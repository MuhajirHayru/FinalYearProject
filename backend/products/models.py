import uuid

from django.conf import settings
from django.db import models

from .geo import haversine_km


class ProductStatus(models.TextChoices):
    """Product listing lifecycle (fig 3.10)."""

    DRAFT = "DRAFT", "Draft"
    ACTIVE = "ACTIVE", "Active"
    INACTIVE = "INACTIVE", "Inactive"
    SOLD = "SOLD", "Sold"
    DELETED = "DELETED", "Deleted"


class ProductType(models.TextChoices):
    FARMER_LISTING = "FARMER_LISTING", "Farmer Listing"
    WHOLESALER_LISTING = "WHOLESALER_LISTING", "Wholesaler Listing"


class Category(models.TextChoices):
    VEGETABLES = "Vegetables", "Vegetables"
    FRUITS = "Fruits", "Fruits"
    GRAINS = "Grains", "Grains"
    PULSES = "Pulses", "Pulses"
    SPICES = "Spices", "Spices"
    ROOT_CROPS = "Root Crops", "Root Crops"
    OTHER = "Other", "Other"


class UnitOfMeasure(models.TextChoices):
    KG = "kg", "Kilogram"
    QUINTAL = "quintal", "Quintal"
    TON = "ton", "Metric ton"
    PIECE = "piece", "Piece"
    CRATE = "crate", "Crate"
    BUNCH = "bunch", "Bunch"
    LITRE = "litre", "Litre"


class ProductQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status=ProductStatus.ACTIVE)

    def of_type(self, product_type):
        return self.filter(product_type=product_type)

    def visible_to(self, user):
        """Data isolation between roles (doc 3.8, NFR-04).

        Owners always see their own listings regardless of status; every other
        viewer sees only ACTIVE listings from an APPROVED counterparty.
        """
        from users.models import AccountStatus

        return self.filter(
            models.Q(owner=user)
            | models.Q(
                status=ProductStatus.ACTIVE,
                owner__status=AccountStatus.APPROVED,
            )
        ).distinct()


class Product(models.Model):
    """Unified listing table backing both FARMER_LISTING and WHOLESALER_LISTING.

    Physical schema follows table 4.2 of the doc; the owning user is the
    Farmer (FR-F-04) or Wholesaler (FR-W-05) depending on ``product_type``.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    category = models.CharField(
        max_length=100, choices=Category.choices, default=Category.VEGETABLES
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit_of_measure = models.CharField(
        max_length=50, choices=UnitOfMeasure.choices, default=UnitOfMeasure.KG
    )
    price_per_unit = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=20, choices=ProductStatus.choices, default=ProductStatus.ACTIVE
    )
    product_type = models.CharField(
        max_length=25, choices=ProductType.choices, default=ProductType.FARMER_LISTING
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="products"
    )
    images = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        db_table = "products"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["product_type", "status"]),
            models.Index(fields=["category"]),
            models.Index(fields=["owner", "product_type"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_product_type_display()})"

    # -- listing lifecycle (doc 4.5) -------------------------------------
    def activate(self):
        if self.status == ProductStatus.DELETED:
            raise ValueError("A deleted listing cannot be reactivated.")
        self.status = ProductStatus.ACTIVE
        self.save(update_fields=["status", "updated_at"])
        return self

    def deactivate(self):
        self.status = ProductStatus.INACTIVE
        self.save(update_fields=["status", "updated_at"])
        return self

    def mark_sold(self):
        self.status = ProductStatus.SOLD
        self.quantity = 0
        self.save(update_fields=["status", "quantity", "updated_at"])
        return self

    def mark_deleted(self):
        self.status = ProductStatus.DELETED
        self.save(update_fields=["status", "updated_at"])
        return self

    def replenish(self, quantity):
        """Stock topped back up: SOLD/INACTIVE -> ACTIVE (fig 3.10)."""
        self.quantity = quantity
        self.status = ProductStatus.ACTIVE
        self.save(update_fields=["quantity", "status", "updated_at"])
        return self

    # -- helpers ---------------------------------------------------------
    @property
    def is_farmer_listing(self):
        return self.product_type == ProductType.FARMER_LISTING

    @property
    def total_value(self):
        return self.quantity * self.price_per_unit

    def distance_from(self, user):
        """Great-circle distance in km from ``user``; None when either side
        lacks coordinates."""
        if (
            user is None
            or user.latitude is None
            or user.longitude is None
            or self.owner.latitude is None
            or self.owner.longitude is None
        ):
            return None
        return haversine_km(
            float(user.latitude),
            float(user.longitude),
            float(self.owner.latitude),
            float(self.owner.longitude),
        )
