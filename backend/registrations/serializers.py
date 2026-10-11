from datetime import date
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from rest_framework import serializers

from products.models import Category
from users.models import Role

from .models import (
    AdministratorScope,
    AdministrativeLocation,
    AgriculturalProductType,
    RegistrationDocument,
    RegistrationProductSelection,
    RegistrationReview,
    UserRegistration,
)
from .services import (
    admin_scope_type_for_location,
    can_assign_admin_scope,
    required_license_types_for_role,
)

MAX_LICENSE_BYTES = 10 * 1024 * 1024
LICENSE_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
SEX_CHOICES = (
    ("FEMALE", "Female"),
    ("MALE", "Male"),
    ("OTHER", "Other"),
    ("PREFER_NOT_TO_SAY", "Prefer not to say"),
)


class LocationSerializer(serializers.ModelSerializer):
    level_display = serializers.CharField(source="get_level_display", read_only=True)
    has_children = serializers.SerializerMethodField()

    class Meta:
        model = AdministrativeLocation
        fields = [
            "id",
            "source_id",
            "name",
            "alternative_names",
            "level",
            "level_display",
            "has_children",
        ]

    def get_has_children(self, obj):
        return obj.children.filter(active=True).exists()


class AgriculturalProductTypeSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = AgriculturalProductType
        fields = ["id", "code", "name", "category", "category_display"]


class RegistrationProductSelectionInputSerializer(serializers.Serializer):
    product_type = serializers.PrimaryKeyRelatedField(
        queryset=AgriculturalProductType.objects.filter(
            active=True,
            category__in=(Category.VEGETABLES, Category.ROOT_CROPS, Category.FRUITS),
        )
    )
    intent = serializers.ChoiceField(choices=RegistrationProductSelection.Intent.choices)


class RegistrationDraftSerializer(serializers.Serializer):
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    sex = serializers.ChoiceField(
        choices=SEX_CHOICES, required=False, allow_blank=True
    )
    business_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    business_address = serializers.CharField(max_length=500, required=False, allow_blank=True)
    location = serializers.PrimaryKeyRelatedField(
        queryset=AdministrativeLocation.objects.filter(active=True),
        required=False,
        allow_null=True,
    )
    product_selections = RegistrationProductSelectionInputSerializer(
        many=True, required=False
    )

    def validate_date_of_birth(self, value):
        if value is None:
            return value
        today = date.today()
        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if value > today or age > 120:
            raise serializers.ValidationError("Enter a valid date of birth.")
        return value

    def validate_phone(self, value):
        normalized = value.strip()
        if normalized and any(not (char.isdigit() or char in "+ -()") for char in normalized):
            raise serializers.ValidationError("Enter a valid phone number.")
        return normalized

    def validate_product_selections(self, selections):
        keys = [(row["product_type"].pk, row["intent"]) for row in selections]
        if len(keys) != len(set(keys)):
            raise serializers.ValidationError("Remove duplicate product selections.")
        return selections

    def validate(self, attrs):
        user = self.context["request"].user
        selections = attrs.get("product_selections")
        if selections is not None:
            allowed = {
                Role.FARMER: {RegistrationProductSelection.Intent.PRODUCES},
                Role.WHOLESALER: {
                    RegistrationProductSelection.Intent.BUYS,
                    RegistrationProductSelection.Intent.SELLS,
                    RegistrationProductSelection.Intent.HANDLES,
                },
                Role.RETAILER: {RegistrationProductSelection.Intent.BUYS},
            }[user.role]
            invalid = [
                row["intent"]
                for row in selections
                if row["intent"] not in allowed
            ]
            if invalid:
                raise serializers.ValidationError(
                    {"product_selections": "Product selections do not match your role."}
                )
        if user.role in (Role.WHOLESALER, Role.RETAILER) and attrs.get("date_of_birth"):
            return attrs
        return attrs

    def update(self, registration, validated_data):
        selections = validated_data.pop("product_selections", None)
        user = registration.user
        if "location" in validated_data:
            location = validated_data.get("location")
            if location and not location.active:
                raise serializers.ValidationError({"location": "Select an active location."})
            registration.location = location
            user.location = " → ".join(
                reversed(_location_names(location))
            ) if location else ""
        for key, value in validated_data.items():
            setattr(registration, key, value)
        user.save(update_fields=["location", "updated_at"])
        registration.save()
        if selections is not None:
            registration.product_selections.all().delete()
            RegistrationProductSelection.objects.bulk_create(
                [
                    RegistrationProductSelection(
                        registration=registration,
                        product_type=row["product_type"],
                        intent=row["intent"],
                    )
                    for row in selections
                ]
            )
        return registration


def _location_names(location):
    names = []
    while location is not None:
        names.append(location.name)
        location = location.parent
    return names


class RegistrationSubmissionSerializer(serializers.Serializer):
    confirm = serializers.BooleanField()

    def validate_confirm(self, value):
        if not value:
            raise serializers.ValidationError("Confirm the registration before submitting.")
        return value


class RegistrationDocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()

    def validate_file(self, value):
        extension = Path(value.name).suffix.lower()
        if extension not in LICENSE_EXTENSIONS:
            raise serializers.ValidationError("Upload a PDF, JPG, JPEG, or PNG document.")
        if value.size <= 0 or value.size > MAX_LICENSE_BYTES:
            raise serializers.ValidationError("Documents must be no larger than 10 MB.")
        header = value.read(16)
        value.seek(0)
        if extension == ".pdf":
            if not header.startswith(b"%PDF-"):
                raise serializers.ValidationError("The file is not a valid PDF.")
        else:
            try:
                image = Image.open(value)
                if image.format not in ("JPEG", "PNG"):
                    raise serializers.ValidationError("Upload a valid JPEG or PNG image.")
                image.verify()
            except (UnidentifiedImageError, OSError, ValueError):
                raise serializers.ValidationError("Upload a valid JPEG or PNG image.")
            finally:
                value.seek(0)
        return value


class RegistrationDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegistrationDocument
        fields = [
            "id",
            "document_type",
            "original_filename",
            "verification_status",
            "verification_note",
            "uploaded_at",
        ]
        read_only_fields = fields


class RegistrationReviewSerializer(serializers.ModelSerializer):
    reviewer_name = serializers.CharField(source="reviewer.full_name", read_only=True)

    class Meta:
        model = RegistrationReview
        fields = ["id", "reviewer_name", "action", "reason", "created_at"]
        read_only_fields = fields


class RegistrationDetailsSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    role = serializers.CharField(source="user.role", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True, default="")
    location_path = serializers.SerializerMethodField()
    location_id_path = serializers.SerializerMethodField()
    product_selections = serializers.SerializerMethodField()
    documents = RegistrationDocumentSerializer(many=True, read_only=True)
    review_history = RegistrationReviewSerializer(many=True, read_only=True)

    class Meta:
        model = UserRegistration
        fields = [
            "id", "user", "full_name", "email", "phone", "role",
            "date_of_birth", "sex", "business_name", "business_address",
            "location", "location_name", "location_path", "location_id_path", "product_selections",
            "documents", "status", "legacy_registration", "submitted_at",
            "review_history", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_location_path(self, obj):
        if not obj.location_id:
            return []
        return list(reversed(_location_names(obj.location)))

    def get_location_id_path(self, obj):
        if not obj.location_id:
            return []
        identifiers = []
        location = obj.location
        while location is not None:
            identifiers.append(str(location.pk))
            location = location.parent
        return list(reversed(identifiers))

    def get_product_selections(self, obj):
        return [
            {
                "id": str(selection.product_type_id),
                "name": selection.product_type.name,
                "category": selection.product_type.category,
                "intent": selection.intent,
            }
            for selection in obj.product_selections.select_related("product_type")
        ]


class RegistrationDecisionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=("APPROVE", "REJECT", "REQUEST_CHANGES")
    )
    reason = serializers.CharField(required=False, allow_blank=True, max_length=2000)

    def validate(self, attrs):
        action = attrs["action"]
        reason = (attrs.get("reason") or "").strip()
        if action in ("REJECT", "REQUEST_CHANGES") and not reason:
            raise serializers.ValidationError(
                {"reason": "A reason is required for this decision."}
            )
        attrs["reason"] = reason
        return attrs


class LicenseVerificationSerializer(serializers.Serializer):
    verified = serializers.BooleanField()
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000)

    def validate(self, attrs):
        if not attrs["verified"] and not (attrs.get("note") or "").strip():
            raise serializers.ValidationError(
                {"note": "Explain why the license needs correction."}
            )
        return attrs


class AdminScopeSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.full_name", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True, default="")
    location_level = serializers.CharField(source="location.level", read_only=True, default="")
    location_path = serializers.SerializerMethodField()
    scope_label = serializers.SerializerMethodField()
    scope_type = serializers.SerializerMethodField()
    account_status = serializers.CharField(source="user.status", read_only=True)
    user_count = serializers.SerializerMethodField()
    admin_count = serializers.SerializerMethodField()

    class Meta:
        model = AdministratorScope
        fields = [
            "id",
            "user",
            "user_name",
            "user_email",
            "account_status",
            "level",
            "location",
            "location_name",
            "location_level",
            "location_path",
            "scope_label",
            "scope_type",
            "user_count",
            "admin_count",
        ]
        read_only_fields = ["id", "user_name", "user_email", "location_name"]
        extra_kwargs = {"user": {"required": False}}

    def get_location_path(self, obj):
        if not obj.location_id:
            return []
        return list(reversed(_location_names(obj.location)))

    def get_scope_label(self, obj):
        if obj.level == AdministratorScope.Level.GLOBAL:
            return "Top-Level User Admin (Nationwide)"
        return {
            "REGIONAL": "Regional Admin",
            "CITY": "City Administration Admin",
            "ZONAL": "Zonal Admin",
            "WOREDA": "Woreda Admin",
            "SUBCITY": "Sub-city Admin",
            "DISTRICT": "District Admin",
        }.get(admin_scope_type_for_location(obj.location), "Administrative Division Admin")

    def get_scope_type(self, obj):
        return (
            "TOP_LEVEL"
            if obj.level == AdministratorScope.Level.GLOBAL
            else admin_scope_type_for_location(obj.location)
        )

    def get_user_count(self, obj):
        if not obj.location_id:
            return UserRegistration.objects.filter(
                user__role__in=(Role.FARMER, Role.WHOLESALER, Role.RETAILER)
            ).count()
        from .services import location_descendant_ids

        return UserRegistration.objects.filter(
            location_id__in=location_descendant_ids(obj.location),
            user__role__in=(Role.FARMER, Role.WHOLESALER, Role.RETAILER),
        ).count()

    def get_admin_count(self, obj):
        if not obj.location_id:
            return AdministratorScope.objects.filter(
                user__role=Role.USER_ADMIN,
                user__status="APPROVED",
            ).exclude(user_id=obj.user_id).count()
        from .services import location_descendant_ids

        return AdministratorScope.objects.filter(
            level=AdministratorScope.Level.LOCATION,
            location_id__in=location_descendant_ids(obj.location),
            user__role=Role.USER_ADMIN,
            user__status="APPROVED",
        ).exclude(user_id=obj.user_id).count()

    def validate(self, attrs):
        user = attrs.get("user", getattr(self.instance, "user", None))
        level = attrs.get("level", getattr(self.instance, "level", None))
        location = attrs.get("location", getattr(self.instance, "location", None))
        if user and user.role != Role.USER_ADMIN:
            raise serializers.ValidationError({"user": "Only User Admins may be assigned a scope."})
        if level == AdministratorScope.Level.GLOBAL:
            if location is not None:
                raise serializers.ValidationError({"location": "Global scope must not have a location."})
        elif level == AdministratorScope.Level.LOCATION:
            if location is None or not location.active:
                raise serializers.ValidationError({"location": "Choose an active administrative location."})
        else:
            raise serializers.ValidationError({"level": "Choose GLOBAL or LOCATION scope."})
        request = self.context.get("request")
        if request and user and not can_assign_admin_scope(
            request.user,
            level,
            location,
            admin_scope_type_for_location(location) if location else "TOP_LEVEL",
        ):
            raise serializers.ValidationError(
                {"location": "You cannot assign an administrator outside your permitted scope."}
            )
        return attrs


def registration_can_be_submitted(registration, user):
    if not user.full_name.strip() or not user.phone.strip():
        raise serializers.ValidationError(
            {"personal_information": "Full name and phone number are required."}
        )
    if registration.location_id is None or not registration.location.active:
        raise serializers.ValidationError(
            {"location": "Choose a valid administrative location."}
        )
    required_document_types = required_license_types_for_role(user.role)
    if required_document_types and not registration.documents.filter(
        document_type__in=required_document_types
    ).exists():
        raise serializers.ValidationError(
            {"documents": "Upload the license required for your registration role."}
        )
    if not registration.product_selections.exists():
        raise serializers.ValidationError(
            {"product_selections": "Select at least one agricultural product type."}
        )
    if user.role == Role.FARMER:
        if not registration.date_of_birth or not registration.sex:
            raise serializers.ValidationError(
                {"personal_information": "Date of birth and sex are required for farmers."}
            )
    elif not registration.business_name.strip():
        raise serializers.ValidationError(
            {"business_name": "Business name is required for this role."}
        )
