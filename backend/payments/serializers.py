from decimal import Decimal

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from products.models import Product, ProductType
from users.models import Role, User

from .bank_accounts import encrypt_account_number, normalize_account_number
from .models import (
    BankAccount,
    BankAccountStatus,
    BusinessAgreement,
    Order,
    OrderStatus,
    PayoutBank,
    PaymentRecord,
    Review,
    Wallet,
    WalletFundingRequest,
    WalletPayoutRequest,
    WalletTransaction,
)


class PayoutBankSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayoutBank
        fields = ["id", "code", "name", "source_url"]
        read_only_fields = fields


class BankAccountSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(read_only=True)
    user_name = serializers.CharField(source="user.full_name", read_only=True)
    user_role = serializers.CharField(source="user.role", read_only=True)
    bank_name = serializers.CharField(source="bank.name", read_only=True)
    masked_account_number = serializers.CharField(read_only=True)
    payout_requests = serializers.SerializerMethodField()
    account_number = serializers.CharField(
        write_only=True, required=False, trim_whitespace=True, max_length=64
    )
    confirm_account_number = serializers.CharField(
        write_only=True, required=False, trim_whitespace=True, max_length=64
    )

    class Meta:
        model = BankAccount
        fields = [
            "id", "user_id", "user_name", "user_role", "bank", "bank_name",
            "account_holder_name", "account_number", "confirm_account_number",
            "masked_account_number", "branch", "branch_code", "account_type",
            "nickname", "status", "is_default", "payout_requests",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "user_id", "user_name", "user_role", "bank_name",
            "masked_account_number", "status", "created_at", "updated_at",
            "payout_requests",
        ]

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_payout_requests(self, obj):
        return [
            {
                "id": str(request.pk),
                "amount": str(request.amount),
                "status": request.status,
                "submitted_at": request.submitted_at,
            }
            for request in obj.payout_requests.all()[:5]
        ]

    def validate_account_holder_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Enter the account holder's legal name.")
        return value

    def validate_bank(self, value):
        if not value.is_active:
            raise serializers.ValidationError("This bank is not available for registration.")
        return value

    def validate(self, attrs):
        account_number = attrs.get("account_number")
        confirmation = attrs.get("confirm_account_number")
        if self.instance is None and (not account_number or not confirmation):
            raise serializers.ValidationError(
                {"account_number": "Enter and confirm the account number."}
            )
        if account_number is not None or confirmation is not None:
            if not account_number or not confirmation:
                raise serializers.ValidationError(
                    {"confirm_account_number": "Enter the account number twice to change it."}
                )
            try:
                normalized = normalize_account_number(account_number)
                confirmed = normalize_account_number(confirmation)
            except ValueError as exc:
                raise serializers.ValidationError({"account_number": str(exc)}) from exc
            if normalized != confirmed:
                raise serializers.ValidationError(
                    {"confirm_account_number": "Account numbers do not match."}
                )
        return attrs

    def create(self, validated_data):
        validated_data.pop("confirm_account_number", None)
        account_number = validated_data.pop("account_number")
        encrypted, last4 = encrypt_account_number(account_number)
        validated_data["account_number_encrypted"] = encrypted
        validated_data["account_number_last4"] = last4
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("confirm_account_number", None)
        account_number = validated_data.pop("account_number", None)
        if account_number is not None:
            encrypted, last4 = encrypt_account_number(account_number)
            validated_data["account_number_encrypted"] = encrypted
            validated_data["account_number_last4"] = last4
        return super().update(instance, validated_data)


class PaymentRecordSerializer(serializers.ModelSerializer):
    wholesaler = serializers.CharField(source="submitted_by.full_name", read_only=True)
    wholesaler_id = serializers.UUIDField(source="submitted_by_id", read_only=True)
    farmer_name = serializers.CharField(source="farmer.full_name", read_only=True)
    product_title = serializers.CharField(source="product.title", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    method_display = serializers.CharField(
        source="get_payment_method_display", read_only=True
    )
    verified_by_name = serializers.CharField(
        source="verified_by.full_name", read_only=True, default=None
    )
    submitted = serializers.DateTimeField(
        source="submitted_at", read_only=True, format="%d %b %Y"
    )
    display_id = serializers.CharField(read_only=True)
    total = serializers.SerializerMethodField()

    submitted_by = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role=Role.WHOLESALER)
    )
    farmer = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role=Role.FARMER)
    )
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(
            product_type__in=[
                ProductType.FARMER_LISTING,
                ProductType.WHOLESALER_LISTING,
            ]
        )
    )

    class Meta:
        model = PaymentRecord
        fields = [
            "id", "display_id", "submitted_by", "submitted_by_id", "wholesaler",
            "wholesaler_id", "farmer", "farmer_name", "product", "product_title",
            "amount", "total", "payment_method", "method_display",
            "reference_number", "status", "status_display", "verified_by",
            "verified_by_name", "notes", "submitted_at", "submitted", "verified_at",
        ]
        read_only_fields = [
            "id", "display_id", "status", "verified_by", "verified_at", "notes",
        ]

    @extend_schema_field(serializers.CharField)
    def get_total(self, obj):
        return f"{obj.amount:,.2f} ETB"

    def validate(self, attrs):
        request = self.context.get("request")
        if request is None or request.method != "POST":
            return attrs

        actor = request.user
        if actor.role != Role.WHOLESALER:
            raise serializers.ValidationError("Only wholesalers can submit payments.")
        if attrs["submitted_by"].pk != actor.pk:
            raise serializers.ValidationError("You can only submit payments for yourself.")
        if attrs["farmer"] == actor:
            raise serializers.ValidationError("The farmer must be a different user.")

        product = attrs["product"]
        if product.owner_id != attrs["farmer"].pk:
            raise serializers.ValidationError(
                "The selected product does not belong to the selected farmer."
            )
        if attrs.get("amount", 0) <= 0:
            raise serializers.ValidationError({"amount": "Amount must be positive."})
        return attrs


class OrderSerializer(serializers.ModelSerializer):
    wholesaler_name = serializers.CharField(source="wholesaler.full_name", read_only=True)
    farmer_name = serializers.CharField(
        source="farmer.full_name", read_only=True, allow_null=True
    )
    retailer_name = serializers.CharField(
        source="retailer.full_name", read_only=True, allow_null=True
    )
    buyer_name = serializers.SerializerMethodField()
    seller_name = serializers.SerializerMethodField()
    buyer_financially_verified = serializers.BooleanField(
        source="buyer.financially_verified", read_only=True
    )
    seller_is_online = serializers.BooleanField(source="seller.is_online", read_only=True)
    product_title = serializers.CharField(source="product.title", read_only=True)
    date = serializers.DateTimeField(source="created_at", read_only=True, format="%b %d, %Y")
    total = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    allowed_transitions = serializers.SerializerMethodField()
    agreement_status = serializers.SerializerMethodField()
    payment_status_display = serializers.CharField(
        source="get_payment_status_display", read_only=True
    )

    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(
            product_type__in=[
                ProductType.FARMER_LISTING,
                ProductType.WHOLESALER_LISTING,
            ]
        )
    )

    class Meta:
        model = Order
        fields = [
            "id", "reference", "wholesaler", "wholesaler_name", "farmer",
            "farmer_name", "retailer", "retailer_name", "buyer_name", "seller_name",
            "buyer_financially_verified", "seller_is_online",
            "product", "product_title", "quantity",
            "total_amount", "total", "status", "status_display",
            "payment_status", "payment_status_display", "delivery_information",
            "delivered_at", "quality_confirmed_at", "dispute_reason",
            "agreement_status", "allowed_transitions", "date", "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id", "reference", "wholesaler", "farmer", "total_amount",
            "status", "created_at", "updated_at",
        ]

    @extend_schema_field(serializers.CharField)
    def get_total(self, obj):
        return f"{obj.total_amount:,.2f} ETB"

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_allowed_transitions(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        allowed = list(obj.ALLOWED_TRANSITIONS.get(obj.status, ()))
        if user is None or not user.is_authenticated:
            return []
        if obj.status == OrderStatus.PENDING_SELLER_APPROVAL:
            if user != obj.seller:
                return [OrderStatus.CANCELLED] if user == obj.buyer else []
            return [
                OrderStatus.ACCEPTED,
                OrderStatus.REJECTED,
            ]
        if obj.status in (OrderStatus.ACCEPTED, OrderStatus.PROCESSING):
            if user == obj.seller:
                return [
                    status for status in allowed
                    if status in (OrderStatus.PROCESSING, OrderStatus.CONFIRMED, OrderStatus.SHIPPED)
                ]
            if user == obj.buyer and OrderStatus.CANCELLED in allowed:
                return [OrderStatus.CANCELLED]
            return []
        if obj.status == OrderStatus.SHIPPED:
            return (
                [OrderStatus.DELIVERED]
                if user == obj.buyer
                else []
            )
        if obj.status in (
            OrderStatus.AWAITING_QUALITY_CONFIRMATION,
            OrderStatus.AWAITING_PAYMENT_RELEASE,
            OrderStatus.DISPUTED,
        ):
            return []
        return allowed if user in (obj.buyer, obj.seller) else []

    @extend_schema_field(serializers.CharField())
    def get_buyer_name(self, obj):
        return obj.buyer.full_name

    @extend_schema_field(serializers.CharField())
    def get_seller_name(self, obj):
        return obj.seller.full_name

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_agreement_status(self, obj):
        agreement = getattr(obj, "agreement", None)
        return agreement.status if agreement else None

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value


class WalletSerializer(serializers.ModelSerializer):
    incoming_total = serializers.SerializerMethodField()
    outgoing_total = serializers.SerializerMethodField()

    class Meta:
        model = Wallet
        fields = [
            "id", "available_balance", "held_balance", "currency", "updated_at",
            "incoming_total", "outgoing_total",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.DecimalField(max_digits=14, decimal_places=2))
    def get_incoming_total(self, obj):
        return sum(
            (
                transaction.amount
                for transaction in obj.transactions.filter(available_delta__gt=0)
            ),
            start=Decimal("0.00"),
        )

    @extend_schema_field(serializers.DecimalField(max_digits=14, decimal_places=2))
    def get_outgoing_total(self, obj):
        return sum(
            (
                -transaction.available_delta
                for transaction in obj.transactions.filter(available_delta__lt=0)
            ),
            start=Decimal("0.00"),
        )


class WalletTransactionSerializer(serializers.ModelSerializer):
    order_reference = serializers.CharField(
        source="order.reference", read_only=True, allow_null=True
    )

    class Meta:
        model = WalletTransaction
        fields = [
            "id", "transaction_type", "amount", "available_delta", "held_delta",
            "reference", "external_reference", "description", "order",
            "order_reference", "created_at",
        ]
        read_only_fields = fields


class WalletFundingRequestSerializer(serializers.ModelSerializer):
    wallet_owner = serializers.CharField(source="wallet.user.full_name", read_only=True)
    wallet_owner_role = serializers.CharField(source="wallet.user.role", read_only=True)
    reviewed_by_name = serializers.CharField(
        source="reviewed_by.full_name", read_only=True, allow_null=True
    )

    class Meta:
        model = WalletFundingRequest
        fields = [
            "id", "wallet", "wallet_owner", "wallet_owner_role", "amount",
            "payment_method", "external_reference", "status", "payment_mode",
            "checkout_url", "provider_status", "provider_transaction_id",
            "verified_amount", "verified_currency", "payment_verified",
            "payment_verified_at", "submitted_at", "reviewed_at",
            "reviewed_by_name", "review_notes",
        ]
        read_only_fields = [
            "id", "wallet", "wallet_owner", "wallet_owner_role", "status",
            "payment_mode", "checkout_url", "provider_status",
            "provider_transaction_id", "verified_amount", "verified_currency",
            "payment_verified", "payment_verified_at", "submitted_at",
            "reviewed_at", "reviewed_by_name", "review_notes",
        ]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate_external_reference(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError(
                "Enter the bank or mobile-money reference for the transfer."
            )
        return value

    def validate_payment_method(self, value):
        if value not in ("CBE Birr", "Telebirr", "Bank Transfer"):
            raise serializers.ValidationError(
                "Funding must be an externally completed bank or mobile-money transfer."
            )
        return value


class ChapaFundingCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0.01")
    )


class WalletPayoutRequestSerializer(serializers.ModelSerializer):
    wallet_owner = serializers.CharField(source="wallet.user.full_name", read_only=True)
    payout_account = serializers.PrimaryKeyRelatedField(
        queryset=BankAccount.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = WalletPayoutRequest
        fields = [
            "id", "wallet", "wallet_owner", "amount", "destination", "status",
            "payout_account", "submitted_at", "reviewed_at",
            "external_reference", "review_notes",
        ]
        read_only_fields = [
            "id", "wallet", "wallet_owner", "status", "submitted_at",
            "reviewed_at", "external_reference", "review_notes",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["destination"].required = False

    def validate(self, attrs):
        payout_account = attrs.get("payout_account")
        request = self.context.get("request")
        if payout_account and (
            request is None or payout_account.user_id != request.user.id
        ):
            raise serializers.ValidationError(
                {"payout_account": "Select one of your own registered accounts."}
            )
        if payout_account:
            attrs["destination"] = (
                f"{payout_account.bank.name} {payout_account.masked_account_number}"
            )
        elif not (attrs.get("destination") or "").strip():
            raise serializers.ValidationError(
                {"destination": "Enter a payout destination or choose a saved bank account."}
            )
        return attrs

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate_destination(self, value):
        value = value.strip()
        return value


class BusinessAgreementSerializer(serializers.ModelSerializer):
    order_reference = serializers.CharField(source="order.reference", read_only=True)
    buyer_name = serializers.CharField(source="order.buyer.full_name", read_only=True)
    seller_name = serializers.CharField(source="order.seller.full_name", read_only=True)
    product_title = serializers.CharField(source="order.product.title", read_only=True)
    total_amount = serializers.DecimalField(
        source="order.total_amount", max_digits=14, decimal_places=2, read_only=True
    )

    class Meta:
        model = BusinessAgreement
        fields = [
            "id", "order", "order_reference", "buyer_name", "seller_name",
            "product_title", "total_amount", "terms", "status", "activated_at",
            "completed_at",
        ]


class ReviewSerializer(serializers.ModelSerializer):
    reviewer_name = serializers.CharField(source="reviewer.full_name", read_only=True)
    reviewee_name = serializers.CharField(source="reviewee.full_name", read_only=True)
    reviewer_role = serializers.CharField(source="reviewer.role", read_only=True)
    reviewee_role = serializers.CharField(source="reviewee.role", read_only=True)
    order_reference = serializers.CharField(source="order.reference", read_only=True)
    verified_transaction = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            "id", "order", "order_reference", "reviewer", "reviewer_name",
            "reviewer_role", "reviewee", "reviewee_name", "reviewee_role",
            "rating", "comment", "created_at", "verified_transaction",
        ]
        read_only_fields = [
            "id", "reviewer", "reviewee", "created_at", "verified_transaction",
        ]

    @extend_schema_field(serializers.BooleanField())
    def get_verified_transaction(self, obj):
        return obj.order.status == OrderStatus.COMPLETED

    def validate_rating(self, value):
        if not 1 <= value <= 5:
            raise serializers.ValidationError("Rating must be between 1 and 5 stars.")
        return value


class FundingReviewDecisionSerializer(serializers.Serializer):
    approve = serializers.BooleanField()
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if not attrs["approve"] and not attrs["notes"].strip():
            raise serializers.ValidationError(
                {"notes": "Provide a reason when rejecting a deposit."}
            )
        return attrs


class PayoutReviewDecisionSerializer(serializers.Serializer):
    approve = serializers.BooleanField()
    external_reference = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")
