import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from products.models import Category

from .storage import PrivateRegistrationStorage


class LocationLevel(models.TextChoices):
    REGION = "REGION", "Region"
    ZONE = "ZONE", "Zone"
    WOREDA = "WOREDA", "Woreda"
    KEBELE = "KEBELE", "Kebele"
    CITY = "CITY", "City"
    SUBCITY = "SUBCITY", "Sub-city"
    DISTRICT = "DISTRICT", "District"
    OTHER = "OTHER", "Other administrative unit"


class AdministrativeLocation(models.Model):
    """Versionable, parent-linked administrative reference data."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_id = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=200)
    alternative_names = models.JSONField(default=list, blank=True)
    level = models.CharField(max_length=20, choices=LocationLevel.choices)
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
    )
    active = models.BooleanField(default=True)
    source_url = models.URLField(max_length=500, blank=True, default="")
    source_version = models.CharField(max_length=64, blank=True, default="")
    verified_on = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "administrative_locations"
        ordering = ["name", "source_id"]
        indexes = [
            models.Index(fields=["parent", "active"]),
            models.Index(fields=["level", "active"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "name"],
                name="reg_loc_parent_name_uq",
            )
        ]

    def clean(self):
        if self.parent_id and self.parent_id == self.pk:
            raise ValidationError({"parent": "A location cannot be its own parent."})
        if self.parent_id and self.parent and self.parent.level == self.level:
            raise ValidationError(
                {"parent": "A location cannot have a parent at the same level."}
            )
        ancestor = self.parent
        while ancestor is not None:
            if self.pk and ancestor.pk == self.pk:
                raise ValidationError({"parent": "Location hierarchy cannot contain a cycle."})
            ancestor = ancestor.parent

    def __str__(self):
        return f"{self.name} ({self.get_level_display()})"


class AdministrativeLocationImport(models.Model):
    """Audit receipt for an idempotent administrative-data import."""

    source_name = models.CharField(max_length=200)
    source_url = models.URLField(max_length=500)
    source_version = models.CharField(max_length=64)
    source_retrieved_on = models.DateField()
    reviewed_on = models.DateField(null=True, blank=True)
    imported_at = models.DateTimeField(auto_now_add=True)
    record_count = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    unchanged_count = models.PositiveIntegerField(default=0)
    inactive_count = models.PositiveIntegerField(default=0)
    coverage_report = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "administrative_location_imports"
        ordering = ["-imported_at"]


class AgriculturalProductType(models.Model):
    """A selectable crop catalog item, independent from marketplace inventory."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=100, choices=Category.choices)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "agricultural_product_types"
        ordering = ["category", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["category", "name"],
                name="reg_prod_cat_name_uq",
            )
        ]
        indexes = [models.Index(fields=["category", "active"])]

    def __str__(self):
        return f"{self.name} ({self.category})"


class RegistrationFieldConfiguration(models.Model):
    class Stage(models.TextChoices):
        INITIAL = "INITIAL", "Initial registration"
        PROFILE = "PROFILE", "Profile completion"

    class FieldKey(models.TextChoices):
        FULL_NAME = "full_name", "Full name"
        EMAIL = "email", "Email address"
        PHONE = "phone", "Phone"
        DATE_OF_BIRTH = "date_of_birth", "Date of birth"
        SEX = "sex", "Sex"
        BUSINESS_NAME = "business_name", "Business name"
        BUSINESS_ADDRESS = "business_address", "Business address"
        LOCATION = "location", "Administrative location"
        PRODUCT_SELECTIONS = "product_selections", "Product interests"

    field_key = models.CharField(max_length=32, choices=FieldKey.choices)
    stage = models.CharField(max_length=16, choices=Stage.choices)
    label = models.CharField(max_length=100)
    description = models.CharField(max_length=300, blank=True, default="")
    required = models.BooleanField(default=False)
    visible = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    roles = models.JSONField(default=list)
    options = models.JSONField(default=list, blank=True)
    editable_after_approval = models.BooleanField(default=False)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registration_field_updates",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "registration_field_configurations"
        ordering = ["stage", "display_order", "field_key"]
        constraints = [
            models.UniqueConstraint(
                fields=["field_key", "stage"],
                name="reg_field_stage_key_uq",
            )
        ]

    def __str__(self):
        return f"{self.label} ({self.stage})"


class RegistrationStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SUBMITTED = "SUBMITTED", "Submitted"
    CHANGES_REQUESTED = "CHANGES_REQUESTED", "Changes Requested"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class UserRegistration(models.Model):
    """Role-specific details kept separate from login identity and account status."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="registration",
    )
    date_of_birth = models.DateField(null=True, blank=True)
    sex = models.CharField(max_length=24, blank=True, default="")
    business_name = models.CharField(max_length=255, blank=True, default="")
    business_address = models.CharField(max_length=500, blank=True, default="")
    location = models.ForeignKey(
        AdministrativeLocation,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="registrations",
    )
    status = models.CharField(
        max_length=24,
        choices=RegistrationStatus.choices,
        default=RegistrationStatus.DRAFT,
    )
    legacy_registration = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    product_types = models.ManyToManyField(
        AgriculturalProductType,
        through="RegistrationProductSelection",
        related_name="registrations",
        blank=True,
    )

    class Meta:
        db_table = "user_registrations"
        indexes = [
            models.Index(fields=["status", "submitted_at"]),
            models.Index(fields=["location", "status"]),
        ]

    def __str__(self):
        return f"{self.user_id} registration ({self.status})"


class RegistrationProductSelection(models.Model):
    class Intent(models.TextChoices):
        PRODUCES = "PRODUCES", "Produces"
        BUYS = "BUYS", "Buys"
        SELLS = "SELLS", "Sells"
        HANDLES = "HANDLES", "Handles"

    registration = models.ForeignKey(
        UserRegistration,
        on_delete=models.CASCADE,
        related_name="product_selections",
    )
    product_type = models.ForeignKey(
        AgriculturalProductType, on_delete=models.PROTECT
    )
    intent = models.CharField(max_length=12, choices=Intent.choices)

    class Meta:
        db_table = "registration_product_selections"
        constraints = [
            models.UniqueConstraint(
                fields=["registration", "product_type", "intent"],
                name="reg_prod_intent_uq",
            )
        ]


def private_document_path(instance, filename):
    extension = Path(filename).suffix.lower()
    return f"{instance.registration.user_id}/{uuid.uuid4().hex}{extension}"


class RegistrationDocument(models.Model):
    class VerificationStatus(models.TextChoices):
        PENDING = "PENDING", "Not Verified"
        VERIFIED = "VERIFIED", "Verified"
        REJECTED = "REJECTED", "Correction Required"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    registration = models.ForeignKey(
        UserRegistration,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    document_type = models.CharField(max_length=40, default="BUSINESS_LICENSE")
    original_filename = models.CharField(max_length=255)
    file = models.FileField(
        storage=PrivateRegistrationStorage(),
        upload_to=private_document_path,
        max_length=500,
    )
    verification_status = models.CharField(
        max_length=16,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
    )
    verification_note = models.TextField(blank=True, default="")
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_registration_documents",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "registration_documents"
        indexes = [
            models.Index(fields=["registration", "verification_status"]),
        ]


class RegistrationReview(models.Model):
    class Action(models.TextChoices):
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CHANGES_REQUESTED = "CHANGES_REQUESTED", "Changes Requested"
        LICENSE_VERIFIED = "LICENSE_VERIFIED", "License Verified"
        LICENSE_REJECTED = "LICENSE_REJECTED", "License Correction Required"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    registration = models.ForeignKey(
        UserRegistration,
        on_delete=models.CASCADE,
        related_name="review_history",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="registration_reviews",
    )
    action = models.CharField(max_length=24, choices=Action.choices)
    reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "registration_reviews"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["registration", "created_at"])]


class AdministratorScope(models.Model):
    class Level(models.TextChoices):
        GLOBAL = "GLOBAL", "Global"
        LOCATION = "LOCATION", "Administrative location"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="administrative_scope",
    )
    level = models.CharField(max_length=12, choices=Level.choices)
    location = models.ForeignKey(
        AdministrativeLocation,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="administrator_scopes",
    )

    class Meta:
        db_table = "administrator_scopes"
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(level="GLOBAL", location__isnull=True)
                    | models.Q(level="LOCATION", location__isnull=False)
                ),
                name="admin_scope_loc_level_ck",
            )
        ]
        indexes = [models.Index(fields=["level", "location"])]

    def clean(self):
        if self.user_id and self.user.role != "USER_ADMIN":
            raise ValidationError({"user": "Only User Admin accounts can have a scope."})
        if (self.level == self.Level.GLOBAL) != (self.location_id is None):
            raise ValidationError(
                {"location": "Global scope has no location; other scopes require one."}
            )

    def __str__(self):
        return f"{self.user_id}: {self.location or self.get_level_display()}"
