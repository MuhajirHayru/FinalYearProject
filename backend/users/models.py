import uuid
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.core.validators import FileExtensionValidator
from django.utils import timezone


class Role(models.TextChoices):
    FARMER = "FARMER", "Farmer"
    WHOLESALER = "WHOLESALER", "Wholesaler"
    RETAILER = "RETAILER", "Retailer"
    USER_ADMIN = "USER_ADMIN", "User Admin"
    FINANCIAL_MANAGER = "FINANCIAL_MANAGER", "Financial Manager"
    SUPER_ADMIN = "SUPER_ADMIN", "Super Admin"


class AccountStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    SUSPENDED = "SUSPENDED", "Suspended"
    DEACTIVATED = "DEACTIVATED", "Deactivated"


class UserQuerySet(models.QuerySet):
    def pending(self):
        return self.filter(status=AccountStatus.PENDING)


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        # Django's is_active flag always mirrors the account status, so a
        # PENDING/REJECTED/SUSPENDED account can never authenticate (fig 3.9).
        if extra.get("status", AccountStatus.APPROVED) != AccountStatus.APPROVED:
            extra.setdefault("is_active", False)
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("status", AccountStatus.APPROVED)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("role", Role.SUPER_ADMIN)
        extra.setdefault("status", AccountStatus.APPROVED)
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self._create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    full_name = models.CharField(max_length=255)
    email = models.EmailField(unique=True, max_length=255)
    phone = models.CharField(max_length=20, blank=True, default="")
    location = models.CharField(max_length=255, blank=True, default="")
    profile_photo = models.ImageField(
        upload_to="profile-photos/%Y/%m/",
        blank=True,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"])],
    )
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    role = models.CharField(max_length=30, choices=Role.choices, default=Role.FARMER)
    status = models.CharField(
        max_length=20, choices=AccountStatus.choices, default=AccountStatus.PENDING
    )
    rejection_reason = models.TextField(blank=True, default="")
    privacy_policy_accepted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    password_changed_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        db_table = "users"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.full_name} ({self.get_role_display()})"

    @property
    def is_approved(self):
        return self.status == AccountStatus.APPROVED

    @property
    def role_display(self):
        return self.get_role_display()

    @property
    def financially_verified(self):
        if self.status != AccountStatus.APPROVED or self.role not in (
            Role.WHOLESALER,
            Role.RETAILER,
        ):
            return False
        from payments.models import FundingStatus, WalletFundingRequest

        return WalletFundingRequest.objects.filter(
            wallet__user_id=self.pk,
            payment_method="Chapa",
            payment_mode="TEST",
            payment_verified=True,
            verified_amount=models.F("amount"),
            verified_currency=models.F("wallet__currency"),
            status=FundingStatus.APPROVED,
        ).exists()

    @property
    def is_online(self):
        if self.status != AccountStatus.APPROVED or self.role not in (
            Role.FARMER,
            Role.WHOLESALER,
        ):
            return False
        timeout = getattr(settings, "PRESENCE_TIMEOUT_SECONDS", 90)
        return PresenceSession.objects.filter(
            user_id=self.pk,
            disconnected_at__isnull=True,
            last_seen_at__gte=timezone.now() - timedelta(seconds=timeout),
        ).exists()

    def approve(self, actor=None):
        """PENDING_APPROVAL -> APPROVED (fig 3.9, FR-UA-02)."""
        self.status = AccountStatus.APPROVED
        self.rejection_reason = ""
        self.is_active = True
        self.save(update_fields=["status", "rejection_reason", "is_active", "updated_at"])
        self._audit(actor, "user_approved")
        return self

    def reject(self, reason="", actor=None):
        """PENDING_APPROVAL -> REJECTED (terminal, fig 3.9)."""
        self.status = AccountStatus.REJECTED
        self.rejection_reason = (reason or "").strip()
        self.is_active = False
        self.save(update_fields=["status", "rejection_reason", "is_active", "updated_at"])
        self._audit(actor, "user_rejected", self.rejection_reason)
        return self

    def suspend(self, actor=None, reason=""):
        """APPROVED -> SUSPENDED."""
        self.status = AccountStatus.SUSPENDED
        self.is_active = False
        self.save(update_fields=["status", "is_active", "updated_at"])
        self._audit(actor, "user_suspended", (reason or "").strip())
        return self

    def reinstate(self, actor=None):
        """SUSPENDED -> APPROVED."""
        self.status = AccountStatus.APPROVED
        self.is_active = True
        self.save(update_fields=["status", "is_active", "updated_at"])
        self._audit(actor, "user_reinstated")
        return self

    def deactivate(self, actor=None):
        """-> DEACTIVATED (terminal)."""
        self.status = AccountStatus.DEACTIVATED
        self.is_active = False
        self.save(update_fields=["status", "is_active", "updated_at"])
        self._audit(actor, "user_deactivated")
        return self

    def _audit(self, actor, action, detail=""):
        """Record an auditable decision trail (NFR-05, doc 4.5)."""
        if actor is None or actor.pk == self.pk:
            return
        AuditLog.objects.create(
            actor=actor, action=action, target=self.email, detail=detail
        )

    def get_role_permissions(self):
        """Introspection helper used by the API layer (doc 4.5)."""
        return list(PERMISSIONS_BY_ROLE.get(self.role, ()))


class PlatformSettings(models.Model):
    """System-wide configuration owned by the Super Admin (FR-SA-04).

    A singleton row (``pk=1``) holding registration policy and the platform
    announcement banner surfaced on every dashboard.
    """

    SINGLETON_PK = 1

    registration_open = models.BooleanField(
        default=True,
        help_text="When False, new public registrations are rejected.",
    )
    require_approval = models.BooleanField(
        default=True,
        help_text="When False, registrations are auto-approved.",
    )
    announcement = models.TextField(
        blank=True,
        default="",
        help_text="Platform-wide announcement shown to every user.",
    )
    maintenance_mode = models.BooleanField(default=False)
    max_failed_login_attempts = models.PositiveSmallIntegerField(
        default=3,
        help_text="Consecutive invalid passwords before a temporary lockout.",
    )
    lockout_duration_minutes = models.PositiveIntegerField(
        default=180,
        help_text=(
            "Duration applied to new lockouts. Existing lockouts expire at their "
            "recorded locked_until time."
        ),
    )
    text_messaging_enabled = models.BooleanField(default=True)
    voice_messaging_enabled = models.BooleanField(default=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="settings_updates",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "platform_settings"
        verbose_name_plural = "platform settings"

    def __str__(self):
        return "Platform settings"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        return obj


def website_asset_path(instance, filename):
    extension = Path(filename).suffix.lower()
    return f"website-assets/{uuid.uuid4().hex}{extension}"


def default_website_content():
    return {
        "landing_badge": "AI-integrated farm-to-marketplace",
        "landing_title": "Connect Ethiopian farmers directly to wholesale buyers",
        "landing_subtitle": "A trusted marketplace for every side of the agricultural trade.",
        "landing_description": (
            "GreenPath connects farmers, wholesalers and retailers with verified "
            "accounts, transparent transactions and secure payments."
        ),
        "landing_primary_button": "Start trading",
        "landing_secondary_button": "Sign in",
        "about_title": "About the platform",
        "about_description": "A single audited platform for agricultural trade.",
        "marketplace_title": "Built for every side of the trade",
        "marketplace_description": "One platform, three commercial roles, and staff oversight.",
        "farmer_description": "List your produce and manage orders.",
        "wholesaler_description": "Source directly from farmers and manage bulk orders.",
        "retailer_description": "Discover wholesale listings and contact suppliers.",
        "feature_verified_title": "Verified accounts",
        "feature_verified_description": "Commercial accounts are reviewed before trading.",
        "feature_payments_title": "Verified payments",
        "feature_payments_description": "Financial Managers verify transfers and resolve disputes.",
        "feature_chat_title": "Real-time chat",
        "feature_chat_description": "Trade conversations stay on the record.",
        "feature_audit_title": "Audited staff actions",
        "feature_audit_description": "Privileged actions are recorded in the audit log.",
        "footer_text": "GreenPath — Farm-to-Marketplace",
        "contact_email": "",
        "contact_phone": "",
    }


class WebsiteContent(models.Model):
    """Persistent public branding and editable website copy."""

    SINGLETON_PK = 1

    platform_name = models.CharField(max_length=80, default="Green Path")
    content = models.JSONField(default=default_website_content, blank=True)
    logo = models.ImageField(
        upload_to=website_asset_path,
        blank=True,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"])],
    )
    favicon = models.ImageField(
        upload_to=website_asset_path,
        blank=True,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp", "ico"])],
    )
    hero_image = models.ImageField(
        upload_to=website_asset_path,
        blank=True,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"])],
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="website_content_updates",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "website_content"
        verbose_name = "website content"
        verbose_name_plural = "website content"

    def __str__(self):
        return self.platform_name

    @classmethod
    def load(cls):
        content, _ = cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        return content


class AuditLog(models.Model):
    """Immutable trail of privileged Super Admin actions (FR-SA-02, FR-SA-03)."""

    id = models.BigAutoField(primary_key=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="audit_entries",
    )
    action = models.CharField(max_length=64)
    target = models.CharField(max_length=255, blank=True, default="")
    detail = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_logs"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["action", "created_at"])]

    def __str__(self):
        return f"{self.action} on {self.target} by {self.actor}"


class PresenceSession(models.Model):
    """One heartbeat lease per authenticated websocket connection."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="presence_sessions"
    )
    last_seen_at = models.DateTimeField(default=timezone.now)
    disconnected_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "user_presence_sessions"
        indexes = [
            models.Index(fields=["user", "disconnected_at", "last_seen_at"]),
        ]


# Endpoint-level permission matrix, surfaced through /api/v1/auth/me/ so the
# frontend can hide navigation the current role may not use.
PERMISSIONS_BY_ROLE = {
    Role.FARMER: (
        "product:create", "product:manage_own", "chat:farmer",
        "dashboard:farmer", "profile:manage",
    ),
    Role.WHOLESALER: (
        "product:discover_farmer", "order:create", "payment:submit",
        "product:create", "product:manage_own", "chat:wholesaler",
        "dashboard:wholesaler", "profile:manage",
    ),
    Role.RETAILER: (
        "product:discover_wholesaler", "chat:retailer",
        "dashboard:retailer", "profile:manage",
    ),
    Role.USER_ADMIN: (
        "user:approve", "user:reject", "user:suspend", "user:list",
        "message:broadcast", "chat:admin", "dashboard:admin",
    ),
    Role.FINANCIAL_MANAGER: (
        "payment:view_all", "payment:verify", "payment:flag",
        "report:financial", "report:export", "dashboard:admin",
    ),
    Role.SUPER_ADMIN: ("*",),
}
