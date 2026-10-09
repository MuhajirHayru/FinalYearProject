from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import AccountStatus, AuditLog, Role, User


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

    def create(self, validated_data):
        password = validated_data.pop("password")
        validated_data["status"] = AccountStatus.PENDING
        # A PENDING account exists but cannot authenticate until a User Admin
        # approves it (fig 3.9), so the Django auth flag starts disabled.
        validated_data["is_active"] = False
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class ProfileUpdateSerializer(serializers.ModelSerializer):
    """Self-service profile edit. Role and status are never client-writable."""

    class Meta:
        model = User
        fields = ["full_name", "phone", "location", "latitude", "longitude"]
        extra_kwargs = {field: {"required": False} for field in fields}

    def validate_latitude(self, value):
        if value is None:
            return value
        if not -90 <= float(value) <= 90:
            raise serializers.ValidationError("Latitude must be between -90 and 90.")
        return value

    def validate_longitude(self, value):
        if value is None:
            return value
        if not -180 <= float(value) <= 180:
            raise serializers.ValidationError("Longitude must be between -180 and 180.")
        return value


class PublicUserSerializer(serializers.ModelSerializer):
    """Counterparty view. Excludes email/coordinates to protect privacy (4.10)."""

    role_display = serializers.CharField(source="get_role_display", read_only=True)
    financially_verified = serializers.BooleanField(read_only=True)
    is_online = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "full_name", "phone", "location", "role",
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
            "privacy_policy_accepted", "created_at", "updated_at",
        ]


class AdminAccountSerializer(serializers.ModelSerializer):
    """Create/modify Admin sub-role accounts (FR-SA-02)."""

    password = serializers.CharField(write_only=True, min_length=8, required=False)
    role_display = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "full_name", "email", "password", "phone", "location",
            "role", "role_display", "status", "is_staff", "created_at",
        ]
        read_only_fields = ["id", "role_display", "created_at"]

    def validate_role(self, value):
        if value not in (Role.USER_ADMIN, Role.FINANCIAL_MANAGER):
            raise serializers.ValidationError(
                "Admin accounts must use the USER_ADMIN or FINANCIAL_MANAGER role."
            )
        return value

    def validate(self, attrs):
        if not attrs.get("password") and self.instance is None:
            raise serializers.ValidationError({"password": "This field is required."})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        validated_data["status"] = AccountStatus.APPROVED
        validated_data.setdefault("privacy_policy_accepted", True)
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class AuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.full_name", read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields = ["id", "actor", "actor_name", "action", "target", "detail", "created_at"]
        read_only_fields = fields


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        # Credentials are checked directly rather than through ``authenticate()``
        # so a PENDING/REJECTED/SUSPENDED account (is_active=False) still gets a
        # precise reason.  The account state is only revealed once the password
        # is proven, so the response never discloses whether an email exists.
        user = User.objects.filter(email__iexact=attrs["email"].strip()).first()
        if user is None or not user.check_password(attrs["password"]):
            raise serializers.ValidationError("Invalid email or password.")
        if user.status == AccountStatus.PENDING:
            raise serializers.ValidationError("Your account is pending admin approval.")
        if user.status in (AccountStatus.REJECTED, AccountStatus.DEACTIVATED):
            raise serializers.ValidationError(
                f"Your account is {user.get_status_display().lower()}."
            )
        if user.status == AccountStatus.SUSPENDED:
            raise serializers.ValidationError("Your account is suspended.")
        if not user.is_active:
            raise serializers.ValidationError("Your account is not active.")
        attrs["user"] = user
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


class PlatformSettingsUpdateSerializer(serializers.Serializer):
    """Body of PATCH /api/v1/superadmin/settings/ (every field optional)."""

    registration_open = serializers.BooleanField(required=False)
    require_approval = serializers.BooleanField(required=False)
    announcement = serializers.CharField(required=False, allow_blank=True)
    maintenance_mode = serializers.BooleanField(required=False)


class AnnouncementSerializer(serializers.Serializer):
    """Body of POST /api/v1/superadmin/announcement/."""

    message = serializers.CharField()
