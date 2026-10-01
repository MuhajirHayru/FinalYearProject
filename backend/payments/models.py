import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from products.models import Product


class PaymentStatus(models.TextChoices):
    """Payment record lifecycle (fig 3.11)."""

    PENDING = "PENDING", "Pending"
    VERIFIED = "VERIFIED", "Verified"
    FLAGGED = "FLAGGED", "Flagged"
    DISPUTED = "DISPUTED", "Disputed"


class PaymentMethod(models.TextChoices):
    CBE_BIRR = "CBE Birr", "CBE Birr"
    TELEBIRR = "Telebirr", "Telebirr"
    BANK_TRANSFER = "Bank Transfer", "Bank Transfer"
    CHAPA = "Chapa", "Chapa"
    CASH = "Cash", "Cash"


class PaymentRecordQuerySet(models.QuerySet):
    def pending(self):
        return self.filter(status=PaymentStatus.PENDING)

    def verified(self):
        return self.filter(status=PaymentStatus.VERIFIED)

    def flagged(self):
        return self.filter(status=PaymentStatus.FLAGGED)

    def for_parties(self, user):
        """Row-level isolation (doc 4.10)."""
        from users.models import Role

        if user.role in (Role.FINANCIAL_MANAGER, Role.SUPER_ADMIN, Role.USER_ADMIN):
            return self
        if user.role == Role.WHOLESALER:
            return self.filter(submitted_by=user)
        return self.filter(farmer=user)


class PaymentRecord(models.Model):
    """Wholesaler-submitted purchase record verified by a Financial Manager."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payments_submitted",
    )
    farmer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payments_received",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    payment_method = models.CharField(
        max_length=100, choices=PaymentMethod.choices, default=PaymentMethod.CBE_BIRR
    )
    reference_number = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments_verified",
    )
    notes = models.TextField(blank=True, default="")
    submitted_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    objects = PaymentRecordQuerySet.as_manager()

    class Meta:
        db_table = "payment_records"
        ordering = ["-submitted_at"]
        indexes = [
            models.Index(fields=["status", "submitted_at"]),
            models.Index(fields=["submitted_by", "status"]),
        ]

    def __str__(self):
        return f"Payment {self.pk} - {self.amount} ETB ({self.status})"

    @property
    def display_id(self):
        return f"#PAY-{str(self.pk)[:8].upper()}"

    # -- verification workflow (doc 4.4.3 PaymentVerificationWorkflow) -----
    def verify(self, financial_manager, notes=""):
        """SUBMITTED|FLAGGED -> VERIFIED."""
        if self.status == PaymentStatus.VERIFIED:
            raise ValueError("Payment is already verified.")
        self.status = PaymentStatus.VERIFIED
        self.verified_by = financial_manager
        self.verified_at = timezone.now()
        if notes:
            self.notes = notes
        self.save(
            update_fields=["status", "verified_by", "verified_at", "notes"]
        )
        return self

    def flag(self, reason=""):
        """SUBMITTED|VERIFIED -> FLAGGED."""
        self.status = PaymentStatus.FLAGGED
        if reason:
            self.notes = reason
        self.save(update_fields=["status", "notes"])
        return self

    def dispute(self, reason=""):
        """FLAGGED -> DISPUTED (terminal, irreconcilable discrepancy)."""
        if self.status != PaymentStatus.FLAGGED:
            raise ValueError("Only a flagged payment can be disputed.")
        self.status = PaymentStatus.DISPUTED
        if reason:
            self.notes = reason
        self.save(update_fields=["status", "notes"])
        return self

    def generate_receipt(self):
        """Audit-friendly receipt payload (doc 4.5 ``generate_receipt``)."""
        return {
            "receipt_id": self.display_id,
            "amount": str(self.amount),
            "currency": "ETB",
            "method": self.payment_method,
            "reference_number": self.reference_number,
            "status": self.status,
            "wholesaler": self.submitted_by.full_name,
            "farmer": self.farmer.full_name,
            "product": self.product.title,
            "submitted_at": self.submitted_at.isoformat(),
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "verified_by": self.verified_by.full_name if self.verified_by else None,
        }


class OrderStatus(models.TextChoices):
    PROCESSING = "Processing", "Processing"
    CONFIRMED = "Confirmed", "Confirmed"
    SHIPPED = "Shipped", "Shipped"
    DELIVERED = "Delivered", "Delivered"
    CANCELLED = "Cancelled", "Cancelled"


class OrderQuerySet(models.QuerySet):
    def open(self):
        return self.exclude(status=OrderStatus.CANCELLED)


class Order(models.Model):
    """Procurement order a wholesaler places against a farmer listing.

    Logistics/delivery tracking is explicitly out of scope (doc 1.4.2); the
    status column records the commercial lifecycle agreed in chat only.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=30, unique=True)
    wholesaler = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="orders_placed",
    )
    farmer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="orders_received",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="orders",
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(
        max_length=20, choices=OrderStatus.choices, default=OrderStatus.PROCESSING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OrderQuerySet.as_manager()

    class Meta:
        db_table = "orders"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["wholesaler", "status"])]

    def __str__(self):
        return f"{self.reference} - {self.wholesaler.full_name}"

    ALLOWED_TRANSITIONS = {
        OrderStatus.PROCESSING: (OrderStatus.CONFIRMED, OrderStatus.CANCELLED),
        OrderStatus.CONFIRMED: (OrderStatus.SHIPPED, OrderStatus.CANCELLED),
        OrderStatus.SHIPPED: (OrderStatus.DELIVERED,),
        OrderStatus.DELIVERED: (),
        OrderStatus.CANCELLED: (),
    }

    def can_transition_to(self, new_status):
        return new_status in self.ALLOWED_TRANSITIONS.get(self.status, ())

    def set_status(self, new_status):
        if new_status not in OrderStatus.values:
            raise ValueError(f"Unknown order status: {new_status}")
        if not self.can_transition_to(new_status):
            raise ValueError(f"Cannot move an order from {self.status} to {new_status}.")
        self.status = new_status
        self.save(update_fields=["status", "updated_at"])
        return self
