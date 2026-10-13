from datetime import timedelta

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers, status
from rest_framework.exceptions import APIException

from registrations.models import (
    AdministrativeLocation,
    AdministratorScope,
    RegistrationFieldConfiguration,
)
from registrations.services import (
    admin_scope_type_for_location,
    can_assign_admin_scope,
)

from .models import (
    AccountStatus,
    AuditLog,
    PlatformSettings,
    Role,
    User,
    WebsiteContent,
    default_website_content,
)


class UserSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source="get_role_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    permissions = serializers.SerializerMethodField()
    financially_verified = serializers.BooleanField(read_only=True)
    is_online = serializers.BooleanField(read_only=True)
    password = serializers.CharField(write_only=True, min_length=8, required=True)

    class Meta:
        model = User
        fields = [
            "id", "full_name", "email", "password", "phone", "location",
            "profile_photo", "latitude", "longitude", "role", "status", "role_display",
            "status_display", "rejection_reason", "privacy_policy_accepted",
            "permissions", "financially_verified", "is_online", "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id", "status", "rejection_reason", "permissions",
            "created_at", "updated_at", "profile_photo",
        ]

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_permissions(self, obj):
        return obj.get_role_permissions()

    def validate_role(self, value):
        # FR-SA-02: admin sub-roles are only granted by the Super Admin.
        if value in (Role.USER_ADMIN, Role.FINANCIAL_MANAGER, Role.SUPER_ADMIN):
            raise serializers.ValidationError("This role cannot self-register.")
        return value

    def validate_privacy_policy_accepted(self, value):
        if not value:
            raise serializers.ValidationError(
                "You must accept the privacy policy and terms of service."
            )
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value.lower()

    def validate(self, attrs):
        role = attrs.get("role")
        if role not in (Role.FARMER, Role.WHOLESALER, Role.RETAILER):
            return attrs
        configurations = {
            field.field_key: field
            for field in RegistrationFieldConfiguration.objects.filter(
                stage=RegistrationFieldConfiguration.Stage.INITIAL
            )
            if role in field.roles
        }
        for field_key in ("full_name", "email"):
            configuration = configurations.get(field_key)
            if configuration is None or not configuration.visible or not configuration.required:
                raise serializers.ValidationError(
                    {field_key: "This required identity field is not configured correctly."}
                )
        phone_configuration = configurations.get("phone")
        if phone_configuration is None:
            raise serializers.ValidationError(
                {"phone": "Phone configuration is unavailable for this role."}
            )
        if not phone_configuration.visible and attrs.get("phone"):
            raise serializers.ValidationError(
                {"phone": "Phone is not available for this registration role."}
            )
        if phone_configuration.required and not attrs.get("phone", "").strip():
            raise serializers.ValidationError({"phone": "Phone is required."})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        config = PlatformSettings.load()
        is_auto_approved = not config.require_approval
        validated_data["status"] = (
            AccountStatus.APPROVED if is_auto_approved else AccountStatus.PENDING
        )
        # A PENDING account exists but cannot authenticate until a User Admin
        # approves it (fig 3.9), so the Django auth flag starts disabled.
        validated_data["is_active"] = is_auto_approved
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class ProfileUpdateSerializer(serializers.ModelSerializer):
    """Self-service profile edit. Role and status are never client-writable."""

    class Meta:
        model = User
        fields = ["full_name", "phone"]
        extra_kwargs = {field: {"required": False} for field in fields}

    def validate(self, attrs):
        errors = {}
        if any(
            field in self.initial_data
            for field in ("location", "latitude", "longitude")
        ):
            errors["location"] = (
                "Update location through Registration details using the configured location list."
            )

        user = self.instance
        for field_key in ("full_name", "phone"):
            if field_key not in attrs:
                continue
            configuration = RegistrationFieldConfiguration.objects.filter(
                stage=RegistrationFieldConfiguration.Stage.PROFILE,
                field_key=field_key,
            ).first()
            if (
                configuration is None
                or user.role not in configuration.roles
                or not configuration.visible
                or not configuration.editable_after_approval
            ):
                errors[field_key] = "This field is not editable in your profile."

        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class PublicUserSerializer(serializers.ModelSerializer):
    """Counterparty view. Excludes email/coordinates to protect privacy (4.10)."""

    role_display = serializers.CharField(source="get_role_display", read_only=True)
    financially_verified = serializers.BooleanField(read_only=True)
    is_online = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "full_name", "role",
            "role_display", "status", "profile_photo", "financially_verified",
            "is_online", "created_at",
        ]


class ProfilePhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["profile_photo"]

    def validate_profile_photo(self, value):
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("Profile images must be 5 MB or smaller.")
        return value


class DirectoryUserSerializer(serializers.ModelSerializer):
    """User Admin / Super Admin view of an account (FR-UA-01, FR-SA-01)."""

    role_display = serializers.CharField(source="get_role_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "full_name", "email", "phone", "location", "role",
            "role_display", "status", "status_display", "rejection_reason",
            "privacy_policy_accepted", "failed_login_attempts", "locked_until",
            "created_at", "updated_at",
        ]


class AdminAccountSerializer(serializers.ModelSerializer):
    """Create/modify staff accounts within the caller's authority."""

    password = serializers.CharField(write_only=True, min_length=8, required=False)
    role_display = serializers.CharField(source="get_role_display", read_only=True)
    scope_label = serializers.SerializerMethodField()
    location_name = serializers.SerializerMethodField()
    last_login = serializers.DateTimeField(read_only=True)
    scope_level = serializers.ChoiceField(
        choices=AdministratorScope.Level.choices,
        write_only=True,
        required=False,
    )
    scope_type = serializers.ChoiceField(
        choices=(
            ("TOP_LEVEL", "Top-Level User Admin"),
            ("REGIONAL", "Regional Admin"),
            ("CITY", "City Administration Admin"),
            ("ZONAL", "Zonal Admin"),
            ("WOREDA", "Woreda Admin"),
            ("SUBCITY", "Sub-city Admin"),
            ("DISTRICT", "District Admin"),
            ("ADMIN_DIVISION", "Administrative Division Admin"),
        ),
        write_only=True,
        required=False,
    )
    scope_location = serializers.PrimaryKeyRelatedField(
        queryset=AdministrativeLocation.objects.filter(active=True),
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = User
        fields = [
            "id", "full_name", "email", "password", "phone", "location",
            "role", "role_display", "status", "is_staff", "created_at",
            "last_login",
            "scope_level", "scope_location", "scope_type", "scope_label",
            "location_name",
        ]
        read_only_fields = ["id", "role_display", "created_at"]

    def validate_role(self, value):
        if value not in (Role.USER_ADMIN, Role.FINANCIAL_MANAGER):
            raise serializers.ValidationError(
                "Admin accounts must use the USER_ADMIN or FINANCIAL_MANAGER role."
            )
        request = self.context.get("request")
        if (
            value == Role.FINANCIAL_MANAGER
            and request
            and request.user.role != Role.SUPER_ADMIN
        ):
            raise serializers.ValidationError(
                "Only the Super Admin can create or manage Financial Managers."
            )
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        if not attrs.get("password") and self.instance is None:
            raise serializers.ValidationError({"password": "This field is required."})
        if attrs.get("role", getattr(self.instance, "role", None)) == Role.USER_ADMIN:
            current_scope = None
            if self.instance is not None:
                current_scope = AdministratorScope.objects.filter(
                    user=self.instance
                ).first()
            scope_level = attrs.get(
                "scope_level",
                current_scope.level if current_scope else None,
            )
            location = attrs.get(
                "scope_location",
                current_scope.location if current_scope else None,
            )
            scope_type = attrs.get(
                "scope_type",
                admin_scope_type_for_location(location) if location else "TOP_LEVEL",
            )
            if scope_level is None:
                raise serializers.ValidationError(
                    {"scope_level": "Choose the new administrator's geographic scope."}
                )
            if scope_level == AdministratorScope.Level.GLOBAL and location is not None:
                raise serializers.ValidationError(
                    {"scope_location": "A global administrator scope has no location."}
                )
            if scope_level == AdministratorScope.Level.LOCATION and location is None:
                raise serializers.ValidationError(
                    {"scope_location": "Choose a location for this administrator."}
                )
            if request and not can_assign_admin_scope(
                request.user,
                scope_level,
                location,
                scope_type,
            ):
                raise serializers.ValidationError(
                    {
                        "scope_location": (
                            "You cannot assign an administrator outside your "
                            "permitted geographic scope."
                        )
                    }
                )
            attrs["scope_type"] = scope_type
        return attrs

    def get_scope_label(self, obj):
        scope = AdministratorScope.objects.filter(user=obj).select_related(
            "location"
        ).first()
        if scope is None:
            return ""
        if scope.level == AdministratorScope.Level.GLOBAL:
            return "Top-Level User Admin (Nationwide)"
        label = {
            "REGIONAL": "Regional Admin",
            "CITY": "City Administration Admin",
            "ZONAL": "Zonal Admin",
            "WOREDA": "Woreda Admin",
            "SUBCITY": "Sub-city Admin",
            "DISTRICT": "District Admin",
        }.get(admin_scope_type_for_location(scope.location), "Administrative Division Admin")
        return label

    def get_location_name(self, obj):
        scope = AdministratorScope.objects.filter(user=obj).select_related(
            "location"
        ).first()
        return scope.location.name if scope and scope.location_id else "Nationwide"

    def create(self, validated_data):
        password = validated_data.pop("password")
        scope_level = validated_data.pop("scope_level", None)
        scope_location = validated_data.pop("scope_location", None)
        validated_data.pop("scope_type", None)
        validated_data["status"] = AccountStatus.APPROVED
        validated_data.setdefault("privacy_policy_accepted", True)
        with transaction.atomic():
            user = User(**validated_data)
            user.set_password(password)
            user.save()
            if user.role == Role.USER_ADMIN:
                AdministratorScope.objects.update_or_create(
                    user=user,
                    defaults={
                        "level": scope_level,
                        "location": scope_location,
                    },
                )
        return user

    def update(self, instance, validated_data):
        scope_level = validated_data.pop("scope_level", None)
        scope_location = validated_data.pop("scope_location", None)
        validated_data.pop("scope_type", None)
        password = validated_data.pop("password", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
            instance.password_changed_at = timezone.now()
        instance.save()
        if scope_level is not None and instance.role == Role.USER_ADMIN:
            AdministratorScope.objects.update_or_create(
                user=instance,
                defaults={"level": scope_level, "location": scope_location},
            )
        return instance


class AuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.full_name", read_only=True, default=None)
    actor_role = serializers.CharField(source="actor.role", read_only=True, default="")

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "actor",
            "actor_name",
            "actor_role",
            "action",
            "target",
            "detail",
            "created_at",
        ]
        read_only_fields = fields


class LoginAttemptError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(
        self,
        message,
        *,
        attempts_remaining,
        max_attempts,
        locked_until=None,
        retry_after_seconds=0,
    ):
        super().__init__(message)
        self.attempts_remaining = attempts_remaining
        self.max_attempts = max_attempts
        self.locked_until = locked_until.isoformat() if locked_until else None
        self.retry_after_seconds = retry_after_seconds


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    @staticmethod
    def _login_error(message, *, attempts_remaining, max_attempts, locked_until=None):
        retry_after_seconds = 0
        if locked_until is not None:
            retry_after_seconds = max(
                1, int((locked_until - timezone.now()).total_seconds() + 0.999)
            )
        return LoginAttemptError(
            message,
            attempts_remaining=attempts_remaining,
            max_attempts=max_attempts,
            locked_until=locked_until,
            retry_after_seconds=retry_after_seconds,
        )

    def validate(self, attrs):
        error = None
        login_error = None
        user = None
        with transaction.atomic():
            user = (
                User.objects.select_for_update()
                .filter(email__iexact=attrs["email"].strip())
                .first()
            )
            if user is None:
                error = "Invalid email or password."
            else:
                now = timezone.now()
                is_locked = user.locked_until and user.locked_until > now
                password_matches = user.check_password(attrs["password"])
                if is_locked:
                    policy = PlatformSettings.load()
                    error = "Sign-in is temporarily locked."
                    login_error = self._login_error(
                        error,
                        attempts_remaining=0,
                        max_attempts=policy.max_failed_login_attempts,
                        locked_until=user.locked_until,
                    )
                elif not password_matches:
                    user.failed_login_attempts += 1
                    policy = PlatformSettings.load()
                    if user.failed_login_attempts >= policy.max_failed_login_attempts:
                        user.locked_until = now + timedelta(
                            minutes=policy.lockout_duration_minutes
                        )
                        user.failed_login_attempts = 0
                        AuditLog.objects.create(
                            actor=None,
                            action="account_login_locked",
                            target=str(user.pk),
                            detail=(
                                "Account locked after consecutive failed password "
                                f"attempts for {policy.lockout_duration_minutes} minutes."
                            ),
                        )
                    else:
                        AuditLog.objects.create(
                            actor=None,
                            action="account_login_failed",
                            target=str(user.pk),
                            detail="Invalid password.",
                        )
                    user.save(
                        update_fields=["failed_login_attempts", "locked_until"]
                    )
                    error = "Invalid email or password."
                    login_error = self._login_error(
                        error,
                        attempts_remaining=(
                            0
                            if user.locked_until and user.locked_until > now
                            else max(
                                0,
                                policy.max_failed_login_attempts
                                - user.failed_login_attempts,
                            )
                        ),
                        max_attempts=policy.max_failed_login_attempts,
                        locked_until=user.locked_until,
                    )
                else:
                    if user.failed_login_attempts or user.locked_until:
                        user.failed_login_attempts = 0
                        user.locked_until = None
                        user.save(
                            update_fields=["failed_login_attempts", "locked_until"]
                        )
                    if user.status == AccountStatus.PENDING:
                        error = "Your account is pending admin approval."
                    elif user.status in (
                        AccountStatus.REJECTED,
                        AccountStatus.DEACTIVATED,
                    ):
                        error = f"Your account is {user.get_status_display().lower()}."
                    elif user.status == AccountStatus.SUSPENDED:
                        error = "Your account is suspended."
                    elif not user.is_active:
                        error = "Your account is not active."
        if login_error:
            raise login_error
        if error:
            raise serializers.ValidationError(error)
        attrs["user"] = user
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    channel = serializers.ChoiceField(choices=("email", "sms"))
    identifier = serializers.CharField(max_length=255, trim_whitespace=True)

    def validate(self, attrs):
        if attrs["channel"] == "email":
            attrs["identifier"] = serializers.EmailField().run_validation(
                attrs["identifier"]
            )
        elif len(attrs["identifier"]) > 20:
            raise serializers.ValidationError(
                {"identifier": "Enter a phone number no longer than 20 characters."}
            )
        return attrs

    def validate_identifier(self, value):
        if not value.strip():
            raise serializers.ValidationError("Enter your email address or phone number.")
        return value.strip()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField(max_length=100)
    token = serializers.CharField(max_length=100)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        from django.utils.encoding import force_str
        from django.utils.http import urlsafe_base64_decode
        from django.contrib.auth.tokens import default_token_generator

        try:
            user_id = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = User.objects.get(pk=user_id)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError("This password reset link is invalid or expired.")

        if not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError("This password reset link is invalid or expired.")
        if user.check_password(attrs["new_password"]):
            raise serializers.ValidationError(
                {"new_password": "Choose a password you have not used before."}
            )
        try:
            validate_password(attrs["new_password"], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": exc.messages})

        attrs["user"] = user
        return attrs


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        user = self.context["request"].user
        if not user.check_password(attrs["current_password"]):
            raise serializers.ValidationError(
                {"current_password": "Current password is incorrect."}
            )
        if user.check_password(attrs["new_password"]):
            raise serializers.ValidationError(
                {"new_password": "Choose a password you have not used before."}
            )
        try:
            validate_password(attrs["new_password"], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": exc.messages})
        return attrs


# ---------------------------------------------------------------------------
# Request bodies for the action-style endpoints (drf-spectacular documentation).
# ---------------------------------------------------------------------------
class RejectUserSerializer(serializers.Serializer):
    """Body of POST /api/v1/admin/users/{id}/reject/."""

    reason = serializers.CharField(required=False, allow_blank=True, default="")


class BroadcastMessageSerializer(serializers.Serializer):
    """Body of POST /api/v1/admin/messages/."""

    message = serializers.CharField()
    role = serializers.ChoiceField(choices=Role.choices, required=False)
    user_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, allow_empty=False
    )

    def validate(self, attrs):
        if not attrs.get("role") and not attrs.get("user_ids"):
            raise serializers.ValidationError(
                "Provide either user_ids or a role to target."
            )
        return attrs


class SuperAdminDecisionSerializer(serializers.Serializer):
    """Body of POST /api/v1/superadmin/users/{id}/override/."""

    decision = serializers.ChoiceField(
        choices=["APPROVE", "REJECT", "SUSPEND", "REACTIVATE"]
    )
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class LoginUnlockSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=1, max_length=500)

    def validate_reason(self, value):
        reason = value.strip()
        if not reason:
            raise serializers.ValidationError("Provide a reason for unlocking this account.")
        return reason


class WebsiteContentUpdateSerializer(serializers.Serializer):
    platform_name = serializers.CharField(max_length=80, required=False, allow_blank=False)
    content = serializers.JSONField(required=False)
    logo = serializers.ImageField(required=False)
    favicon = serializers.ImageField(required=False)
    hero_image = serializers.ImageField(required=False)
    remove_logo = serializers.BooleanField(required=False)
    remove_favicon = serializers.BooleanField(required=False)
    remove_hero_image = serializers.BooleanField(required=False)

    def validate_content(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Website content must be an object.")
        allowed_keys = set(default_website_content())
        unknown_keys = set(value) - allowed_keys
        if unknown_keys:
            raise serializers.ValidationError(
                f"Unsupported content fields: {', '.join(sorted(unknown_keys))}."
            )
        for key, text in value.items():
            if not isinstance(text, str):
                raise serializers.ValidationError({key: "Content values must be text."})
            if len(text) > 2000:
                raise serializers.ValidationError({key: "Content must be 2,000 characters or fewer."})
        return value

    def validate(self, attrs):
        for field in ("logo", "favicon", "hero_image"):
            image = attrs.get(field)
            if image and (image.size <= 0 or image.size > 5 * 1024 * 1024):
                raise serializers.ValidationError(
                    {field: "Images must be non-empty and no larger than 5 MB."}
                )
        return attrs


class PlatformSettingsUpdateSerializer(serializers.Serializer):
    """Body of PATCH /api/v1/superadmin/settings/ (every field optional)."""

    registration_open = serializers.BooleanField(required=False)
    require_approval = serializers.BooleanField(required=False)
    announcement = serializers.CharField(required=False, allow_blank=True)
    maintenance_mode = serializers.BooleanField(required=False)
    max_failed_login_attempts = serializers.IntegerField(
        required=False, min_value=1, max_value=20
    )
    lockout_duration_minutes = serializers.IntegerField(
        required=False, min_value=1, max_value=10080
    )
    text_messaging_enabled = serializers.BooleanField(required=False)
    voice_messaging_enabled = serializers.BooleanField(required=False)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class AnnouncementSerializer(serializers.Serializer):
    """Body of POST /api/v1/superadmin/announcement/."""

    message = serializers.CharField()
