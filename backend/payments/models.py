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
    PENDING_SELLER_APPROVAL = "Pending seller approval", "Pending seller approval"
    ACCEPTED = "Accepted", "Accepted"
    PROCESSING = "Processing", "Processing"
    CONFIRMED = "Confirmed", "Confirmed"
    SHIPPED = "Shipped", "Shipped"
    DELIVERED = "Delivered", "Delivered"
    AWAITING_QUALITY_CONFIRMATION = (
        "Awaiting quality confirmation",
        "Awaiting quality confirmation",
    )
    AWAITING_PAYMENT_RELEASE = "Awaiting payment release", "Awaiting payment release"
    COMPLETED = "Completed", "Completed"
    REJECTED = "Rejected", "Rejected"
    DISPUTED = "Disputed", "Disputed"
    CANCELLED = "Cancelled", "Cancelled"


class OrderPaymentStatus(models.TextChoices):
    RESERVED = "RESERVED", "Reserved"
    HELD = "HELD", "Held in escrow"
    RELEASE_PENDING = "RELEASE_PENDING", "Release pending"
    RELEASED = "RELEASED", "Released"
    REFUNDED = "REFUNDED", "Refunded"
    DISPUTED = "DISPUTED", "Disputed"


class OrderQuerySet(models.QuerySet):
    def open(self):
        return self.exclude(status=OrderStatus.CANCELLED)


class Order(models.Model):
    """Persistent buyer-to-seller order, including the existing legacy flow."""

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
        null=True,
        blank=True,
    )
    retailer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="retail_orders",
        null=True,
        blank=True,
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="orders",
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(
        max_length=40,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING_SELLER_APPROVAL,
    )
    payment_status = models.CharField(
        max_length=24,
        choices=OrderPaymentStatus.choices,
        blank=True,
        default="",
    )
    idempotency_key = models.CharField(max_length=100, blank=True, default="")
    delivery_information = models.TextField(blank=True, default="")
    delivered_at = models.DateTimeField(null=True, blank=True)
    quality_confirmed_at = models.DateTimeField(null=True, blank=True)
    dispute_reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OrderQuerySet.as_manager()

    class Meta:
        db_table = "orders"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["wholesaler", "status"]),
            models.Index(fields=["farmer", "status"]),
            models.Index(fields=["retailer", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="unique_order_idempotency_key",
            )
        ]

    def __str__(self):
        return f"{self.reference} - {self.buyer.full_name}"

    @property
    def buyer(self):
        return self.retailer if self.retailer_id else self.wholesaler

    @property
    def seller(self):
        return self.farmer if self.farmer_id else self.wholesaler

    ALLOWED_TRANSITIONS = {
        OrderStatus.PENDING_SELLER_APPROVAL: (
            OrderStatus.ACCEPTED,
            OrderStatus.REJECTED,
            OrderStatus.CANCELLED,
        ),
        OrderStatus.ACCEPTED: (OrderStatus.PROCESSING, OrderStatus.CANCELLED),
        OrderStatus.AWAITING_QUALITY_CONFIRMATION: (
            OrderStatus.AWAITING_PAYMENT_RELEASE,
            OrderStatus.DISPUTED,
        ),
        OrderStatus.AWAITING_PAYMENT_RELEASE: (OrderStatus.COMPLETED, OrderStatus.DISPUTED),
        OrderStatus.PROCESSING: (
            OrderStatus.CONFIRMED,
            OrderStatus.SHIPPED,
            OrderStatus.CANCELLED,
        ),
        OrderStatus.CONFIRMED: (OrderStatus.SHIPPED, OrderStatus.CANCELLED),
        OrderStatus.SHIPPED: (OrderStatus.DELIVERED,),
        OrderStatus.DELIVERED: (OrderStatus.AWAITING_QUALITY_CONFIRMATION,),
        OrderStatus.COMPLETED: (),
        OrderStatus.REJECTED: (),
        OrderStatus.DISPUTED: (),
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


class AgreementStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"
    DISPUTED = "DISPUTED", "Disputed"


class BusinessAgreement(models.Model):
    """The accepted buyer/seller terms tied to one order."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.OneToOneField(
        Order, on_delete=models.PROTECT, related_name="agreement"
    )
    terms = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=16, choices=AgreementStatus.choices, default=AgreementStatus.ACTIVE
    )
    activated_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "business_agreements"
        ordering = ["-activated_at"]


class Wallet(models.Model):
    """Internal ETB balance. Manual transfers require staff verification."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="wallet"
    )
    available_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    held_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="ETB")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "wallets"


class PayoutBank(models.Model):
    """Maintained list of licensed banks users may register payout accounts with."""

    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=120, unique=True)
    source_url = models.URLField(max_length=500)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "payout_banks"
        ordering = ["name"]

    def __str__(self):
        return self.name


class BankAccountStatus(models.TextChoices):
    NOT_VERIFIED = "NOT_VERIFIED", "Not verified"
    REQUIRES_REVIEW = "REQUIRES_REVIEW", "Requires further review"


class BankAccount(models.Model):
    """User-owned payout account; account number ciphertext is never serialized."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bank_accounts"
    )
    bank = models.ForeignKey(PayoutBank, on_delete=models.PROTECT, related_name="accounts")
    account_holder_name = models.CharField(max_length=255)
    account_number_encrypted = models.TextField()
    account_number_last4 = models.CharField(max_length=4)
    branch = models.CharField(max_length=120, blank=True, default="")
    branch_code = models.CharField(max_length=40, blank=True, default="")
    account_type = models.CharField(max_length=40, blank=True, default="")
    nickname = models.CharField(max_length=80, blank=True, default="")
    status = models.CharField(
        max_length=24,
        choices=BankAccountStatus.choices,
        default=BankAccountStatus.NOT_VERIFIED,
    )
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_bank_accounts"
        ordering = ["-is_default", "-created_at"]
        indexes = [models.Index(fields=["user", "status", "is_default"])]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_default=True),
                name="unique_default_bank_account_per_user",
            )
        ]

    @property
    def masked_account_number(self):
        return f"****{self.account_number_last4}"


class WalletTransactionType(models.TextChoices):
    FUNDING = "FUNDING", "Funding"
    ORDER_RESERVATION = "ORDER_RESERVATION", "Order reservation"
    RESERVATION_RELEASE = "RESERVATION_RELEASE", "Reservation release"
    ESCROW_RELEASE = "ESCROW_RELEASE", "Escrow release"
    PAYOUT_RESERVATION = "PAYOUT_RESERVATION", "Payout reservation"
    PAYOUT = "PAYOUT", "Payout"
    REFUND = "REFUND", "Refund"


class WalletTransaction(models.Model):
    """Append-only accounting entry; deltas describe both wallet balance buckets."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(
        Wallet, on_delete=models.PROTECT, related_name="transactions"
    )
    order = models.ForeignKey(
        Order, on_delete=models.PROTECT, related_name="wallet_transactions",
        null=True, blank=True,
    )
    transaction_type = models.CharField(
        max_length=24, choices=WalletTransactionType.choices
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    available_delta = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    held_delta = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    reference = models.CharField(max_length=100, unique=True)
    external_reference = models.CharField(max_length=255, blank=True, default="")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    description = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "wallet_transactions"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["wallet", "created_at"])]


class FundingStatus(models.TextChoices):
    PENDING = "PENDING", "Pending verification"
    AWAITING_PAYMENT = "AWAITING_PAYMENT", "Awaiting Payment"
    PAYMENT_VERIFICATION_PENDING = (
        "PAYMENT_VERIFICATION_PENDING",
        "Payment Verification Pending",
    )
    AWAITING_APPROVAL = (
        "AWAITING_APPROVAL",
        "Awaiting Financial Admin Approval",
    )
    VERIFIED = "VERIFIED", "Verified"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    FAILED = "FAILED", "Failed"


class WalletFundingRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(
        Wallet, on_delete=models.PROTECT, related_name="funding_requests"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    payment_method = models.CharField(max_length=100)
    external_reference = models.CharField(max_length=255)
    status = models.CharField(
        max_length=32, choices=FundingStatus.choices, default=FundingStatus.PENDING
    )
    payment_mode = models.CharField(max_length=8, default="MANUAL")
    idempotency_key = models.CharField(max_length=100, blank=True, default="")
    checkout_url = models.URLField(max_length=500, blank=True, default="")
    provider_status = models.CharField(max_length=32, blank=True, default="")
    provider_transaction_id = models.CharField(max_length=255, blank=True, default="")
    verified_amount = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    verified_currency = models.CharField(max_length=3, blank=True, default="")
    payment_verified = models.BooleanField(default=False)
    payment_verified_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    review_notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "wallet_funding_requests"
        ordering = ["-submitted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["payment_method", "external_reference"],
                name="unique_wallet_funding_reference",
            ),
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="unique_funding_idempotency_key",
            ),
        ]


class PayoutStatus(models.TextChoices):
    PENDING = "PENDING", "Pending review"
    PAID = "PAID", "Paid"
    REJECTED = "REJECTED", "Rejected"


class WalletPayoutRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(
        Wallet, on_delete=models.PROTECT, related_name="payout_requests"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    destination = models.CharField(max_length=255)
    payout_account = models.ForeignKey(
        BankAccount,
        on_delete=models.SET_NULL,
        related_name="payout_requests",
        null=True,
        blank=True,
    )
    idempotency_key = models.CharField(max_length=100, blank=True, default="")
    status = models.CharField(
        max_length=16, choices=PayoutStatus.choices, default=PayoutStatus.PENDING
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    external_reference = models.CharField(max_length=255, blank=True, default="")
    review_notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "wallet_payout_requests"
        ordering = ["-submitted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="unique_payout_idempotency_key",
            )
        ]


class Review(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="reviews")
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reviews_written"
    )
    reviewee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reviews_received"
    )
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "reviews"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["order", "reviewer", "reviewee"],
                name="unique_order_participant_review",
            ),
            models.CheckConstraint(
                condition=models.Q(rating__gte=1) & models.Q(rating__lte=5),
                name="review_rating_1_to_5",
            ),
        ]
