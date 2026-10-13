from datetime import date
from pathlib import Path

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q

from PIL import Image, UnidentifiedImageError
from rest_framework import serializers

from products.models import Category
from users.models import Role

from .models import (
    AdministratorScope,
    AdministrativeLocation,
    AgriculturalProductType,
    RegistrationDocument,
    RegistrationFieldConfiguration,
    RegistrationProductSelection,
    RegistrationReview,
    RegistrationStatus,
    UserRegistration,
)
from .services import (
    admin_scope_type_for_location,
    can_assign_admin_scope,
    required_license_types_for_role,
)

MAX_LICENSE_BYTES = 10 * 1024 * 1024
LICENSE_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
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


class ManagedAdministrativeLocationSerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source="parent.name", read_only=True, default="")

    class Meta:
        model = AdministrativeLocation
        fields = [
            "id",
            "source_id",
            "name",
            "alternative_names",
            "level",
            "parent",
            "parent_name",
            "active",
        ]

    def validate(self, attrs):
        instance = self.instance or AdministrativeLocation()
        old_parent_id = instance.parent_id
        for field, value in attrs.items():
            setattr(instance, field, value)
        parent = instance.parent
        if parent and instance.active and not parent.active:
            raise serializers.ValidationError(
                {"parent": "An active location must have an active parent."}
            )
        if (
            self.instance
            and self.instance.active
            and not instance.active
            and instance.children.filter(active=True).exists()
        ):
            raise serializers.ValidationError(
                {"active": "Deactivate child locations before deactivating this parent."}
            )
        expected_parent_levels = {
            "REGION": set(),
            "CITY": set(),
            "ZONE": {"REGION"},
            "WOREDA": {"ZONE", "REGION", "CITY", "SUBCITY", "DISTRICT"},
            "KEBELE": {"WOREDA", "DISTRICT"},
            "SUBCITY": {"CITY"},
            "DISTRICT": {"CITY", "SUBCITY", "WOREDA"},
        }
        permitted_parents = expected_parent_levels.get(instance.level)
        if permitted_parents is not None:
            if parent and parent.level not in permitted_parents:
                raise serializers.ValidationError(
                    {"parent": "Choose a parent at a compatible administrative level."}
                )
            if not parent and permitted_parents:
                raise serializers.ValidationError(
                    {"parent": "This administrative level requires a parent."}
                )
            if not parent and not permitted_parents and instance.level not in {
                "REGION",
                "CITY",
            }:
                raise serializers.ValidationError(
                    {"parent": "Choose a parent for this administrative level."}
                )
        if self.instance and old_parent_id != instance.parent_id:
            has_references = (
                instance.children.exists()
                or instance.registrations.exists()
                or instance.administrator_scopes.exists()
            )
            if has_references:
                raise serializers.ValidationError(
                    {"parent": "A referenced location with descendants cannot be moved."}
                )
        try:
            instance.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict)
        return attrs


class ManagedAgriculturalProductTypeSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = AgriculturalProductType
        fields = ["id", "code", "name", "category", "category_display", "active"]
        validators = []

    def validate_code(self, value):
        normalized = value.strip().lower()
        if self.instance and AgriculturalProductType.objects.exclude(
            pk=self.instance.pk
        ).filter(code__iexact=normalized).exists():
            raise serializers.ValidationError("A product option with this code already exists.")
        return normalized

    def validate(self, attrs):
        category = attrs.get(
            "category",
            self.instance.category if self.instance else None,
        )
        if category not in (Category.VEGETABLES, Category.ROOT_CROPS, Category.FRUITS):
            raise serializers.ValidationError(
                {"category": "Registration interests support Vegetables and Fruits only."}
            )
        name = attrs.get("name", self.instance.name if self.instance else "").strip()
        queryset = AgriculturalProductType.objects.filter(
            category=category, name__iexact=name
        )
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if name and queryset.exists():
            raise serializers.ValidationError(
                {"name": "This product option already exists in the selected category."}
            )
        return attrs


PUBLIC_REGISTRATION_ROLES = (Role.FARMER, Role.WHOLESALER, Role.RETAILER)
ALL_ACCOUNT_ROLES = tuple(Role.values)
REQUIRED_FORM_ROLES = {
    "phone": PUBLIC_REGISTRATION_ROLES,
    "full_name": ALL_ACCOUNT_ROLES,
    "location": PUBLIC_REGISTRATION_ROLES,
    "product_selections": PUBLIC_REGISTRATION_ROLES,
    "date_of_birth": (Role.FARMER,),
    "sex": (Role.FARMER,),
    "business_name": (Role.WHOLESALER, Role.RETAILER),
}
SEX_OPTION_VALUES = {"FEMALE", "MALE", "OTHER", "PREFER_NOT_TO_SAY"}


class RegistrationFieldConfigurationSerializer(serializers.ModelSerializer):
    roles = serializers.ListField(
        child=serializers.ChoiceField(choices=Role.choices),
        allow_empty=False,
    )

    class Meta:
        model = RegistrationFieldConfiguration
        fields = [
            "id",
            "field_key",
            "stage",
            "label",
            "description",
            "required",
            "visible",
            "display_order",
            "roles",
            "options",
            "editable_after_approval",
            "updated_at",
        ]
        read_only_fields = ["id", "field_key", "stage", "updated_at"]

    def validate_options(self, value):
        if not isinstance(value, list) or len(value) > 20:
            raise serializers.ValidationError("Provide no more than 20 field options.")
        seen = set()
        for option in value:
            if (
                not isinstance(option, dict)
                or set(option) != {"value", "label"}
                or not isinstance(option["value"], str)
                or not isinstance(option["label"], str)
                or not option["label"].strip()
                or len(option["label"]) > 100
            ):
                raise serializers.ValidationError(
                    "Each option must have a value and a non-empty label of at most 100 characters."
                )
            if option["value"] in seen:
                raise serializers.ValidationError("Field option values must be unique.")
            seen.add(option["value"])
        field_key = (
            self.instance.field_key
            if self.instance
            else self.initial_data.get("field_key")
        )
        if field_key == RegistrationFieldConfiguration.FieldKey.SEX:
            if seen != SEX_OPTION_VALUES:
                raise serializers.ValidationError(
                    "Sex options must retain all supported values."
                )
        elif value:
            raise serializers.ValidationError(
                "Options for this field are managed through its master data."
            )
        return value

    def validate(self, attrs):
        instance = self.instance
        if instance is None:
            raise serializers.ValidationError("Configuration fields cannot be created here.")
        field_key = instance.field_key
        stage = instance.stage
        roles = attrs.get("roles", instance.roles)
        required = attrs.get("required", instance.required)
        visible = attrs.get("visible", instance.visible)
        public_roles = (Role.FARMER, Role.WHOLESALER, Role.RETAILER)
        applicable_roles = (
            public_roles
            if stage == RegistrationFieldConfiguration.Stage.INITIAL
            else REQUIRED_FORM_ROLES.get(field_key, ())
        )
        required_for_all = (
            stage == RegistrationFieldConfiguration.Stage.INITIAL
            and field_key in {"full_name", "email"}
            or stage == RegistrationFieldConfiguration.Stage.PROFILE
            and field_key in REQUIRED_FORM_ROLES
        )
        if any(role not in roles for role in applicable_roles):
            raise serializers.ValidationError(
                {"roles": "This field must remain available for applicable account roles."}
            )
        if required_for_all and (not required or not visible):
            raise serializers.ValidationError(
                {"required": "This field is required and cannot be hidden for applicable roles."}
            )
        if stage == RegistrationFieldConfiguration.Stage.INITIAL and field_key not in {
            "full_name",
            "email",
            "phone",
        }:
            raise serializers.ValidationError(
                {"field_key": "This field cannot be configured for initial registration."}
            )
        if stage == RegistrationFieldConfiguration.Stage.INITIAL and attrs.get(
            "editable_after_approval", instance.editable_after_approval
        ):
            raise serializers.ValidationError(
                {"editable_after_approval": "Initial registration fields cannot be edited after approval."}
            )
        if attrs.get("options") and field_key != RegistrationFieldConfiguration.FieldKey.SEX:
            raise serializers.ValidationError(
                {"options": "Options for this field are managed through its master data."}
            )
        return attrs


class RegistrationProductSelectionInputSerializer(serializers.Serializer):
    product_type = serializers.PrimaryKeyRelatedField(
        queryset=AgriculturalProductType.objects.filter(
            active=True,
            category__in=(Category.VEGETABLES, Category.ROOT_CROPS, Category.FRUITS),
        )
    )
    intent = serializers.ChoiceField(choices=RegistrationProductSelection.Intent.choices)


class RegistrationDraftSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    sex = serializers.CharField(required=False, allow_blank=True, max_length=24)
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        registration = self.context.get("registration")
        if registration is not None:
            previously_selected = registration.product_selections.values_list(
                "product_type_id", flat=True
            )
            self.fields["product_selections"].child.fields[
                "product_type"
            ].queryset = AgriculturalProductType.objects.filter(
                Q(
                    active=True,
                    category__in=(
                        Category.VEGETABLES,
                        Category.ROOT_CROPS,
                        Category.FRUITS,
                    ),
                )
                | Q(pk__in=previously_selected)
            )

    def validate_date_of_birth(self, value):
        if value is None:
            return value
        today = date.today()
        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if value > today or age > 120:
            raise serializers.ValidationError("Enter a valid date of birth.")
        return value

    def validate_sex(self, value):
        if not value:
            return value
        configuration = self._field_configurations().get("sex")
        valid_values = {
            option["value"]
            for option in (configuration.options if configuration else [])
        }
        if value not in valid_values:
            raise serializers.ValidationError("Choose a supported option.")
        return value

    def validate_location(self, value):
        if value and value.children.filter(active=True).exists():
            raise serializers.ValidationError(
                "Choose the most specific active location available."
            )
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
        configurations = self._field_configurations()
        registration = self.context.get("registration")
        is_approved = registration and registration.status == RegistrationStatus.APPROVED
        errors = {}
        for field_key in attrs:
            configuration = configurations.get(field_key)
            if configuration is None or not configuration.visible:
                errors[field_key] = "This field is not available for your role."
            elif is_approved and not configuration.editable_after_approval:
                errors[field_key] = "This field cannot be changed after approval."
        if errors:
            raise serializers.ValidationError(errors)
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

    def _field_configurations(self):
        user = self.context["request"].user
        return {
            field.field_key: field
            for field in RegistrationFieldConfiguration.objects.filter(
                stage=RegistrationFieldConfiguration.Stage.PROFILE,
                visible=True,
            )
            if user.role in field.roles
        }

    def update(self, registration, validated_data):
        selections = validated_data.pop("product_selections", None)
        user = registration.user
        phone_provided = "phone" in validated_data
        phone = validated_data.pop("phone", None)
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
        user_fields = ["updated_at"]
        if "location" in self.initial_data:
            user_fields.append("location")
        if phone_provided:
            user.phone = phone
            user_fields.append("phone")
        user.save(update_fields=user_fields)
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
    values = {
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone,
        "date_of_birth": registration.date_of_birth,
        "sex": registration.sex,
        "business_name": registration.business_name,
        "business_address": registration.business_address,
        "location": registration.location
        if registration.location_id and registration.location.active
        else None,
        "phone": user.phone,
        "product_selections": registration.product_selections.exists(),
    }
    missing = [
        field.field_key
        for field in RegistrationFieldConfiguration.objects.filter(
            stage=RegistrationFieldConfiguration.Stage.PROFILE,
            required=True,
            visible=True,
        )
        if user.role in field.roles
        and (
            not values.get(field.field_key)
            or isinstance(values.get(field.field_key), str)
            and not values[field.field_key].strip()
        )
    ]
    if missing:
        raise serializers.ValidationError(
            {
                field: "This field is required before registration can be submitted."
                for field in missing
            }
        )
    required_document_types = required_license_types_for_role(user.role)
    if required_document_types and not registration.documents.filter(
        document_type__in=required_document_types
    ).exists():
        raise serializers.ValidationError(
            {"documents": "Upload the license required for your registration role."}
        )
