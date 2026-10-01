from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from products.models import Product, ProductType
from users.models import Role, User

from .models import Order, OrderStatus, PaymentRecord


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
        queryset=Product.objects.filter(product_type=ProductType.FARMER_LISTING)
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
    farmer_name = serializers.CharField(source="farmer.full_name", read_only=True)
    product_title = serializers.CharField(source="product.title", read_only=True)
    date = serializers.DateTimeField(source="created_at", read_only=True, format="%b %d, %Y")
    total = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    allowed_transitions = serializers.SerializerMethodField()

    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(product_type=ProductType.FARMER_LISTING)
    )

    class Meta:
        model = Order
        fields = [
            "id", "reference", "wholesaler", "wholesaler_name", "farmer",
            "farmer_name", "product", "product_title", "quantity",
            "total_amount", "total", "status", "status_display",
            "allowed_transitions", "date", "created_at", "updated_at",
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
        return list(obj.ALLOWED_TRANSITIONS.get(obj.status, ()))

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value
