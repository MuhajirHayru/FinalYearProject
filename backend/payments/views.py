"""Payment management endpoints (doc 5.1.5, UC-04, FR-W-04, FR-FM-01..04)."""
import secrets

from django.db import transaction
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from products.models import Product, ProductStatus, ProductType
from users.models import Role
from users.permissions import IsFinancialManager, IsWholesaler

from .models import Order, OrderStatus, PaymentRecord, PaymentStatus
from .serializers import OrderSerializer, PaymentRecordSerializer


def _generate_order_reference():
    """Collision-safe human-readable reference (no count()-based race)."""
    for _ in range(10):
        reference = f"#ORD{secrets.randbelow(900000) + 100000}"
        if not Order.objects.filter(reference=reference).exists():
            return reference
    return f"#ORD{secrets.token_hex(6).upper()}"


class PaymentViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """``/api/v1/payments/`` — Wholesalers submit, Financial Managers verify."""

    serializer_class = PaymentRecordSerializer
    queryset = PaymentRecord.objects.none()  # only for schema lookup-type inference

    def get_queryset(self):
        user = self.request.user
        qs = (
            PaymentRecord.objects.select_related(
                "submitted_by", "farmer", "product", "verified_by"
            )
            .for_parties(user)
        )
        params = self.request.query_params

        status_param = params.get("status")
        if status_param and status_param != "ALL":
            qs = qs.filter(status=status_param)

        method = params.get("method")
        if method and method != "ALL":
            qs = qs.filter(payment_method=method)

        search = (params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                submitted_by__full_name__icontains=search
            ) | qs.filter(
                farmer__full_name__icontains=search
            ) | qs.filter(
                reference_number__icontains=search
            ) | qs.filter(
                product__title__icontains=search
            )
            qs = qs.distinct()

        date_from = params.get("date_from")
        if date_from:
            qs = qs.filter(submitted_at__date__gte=date_from)
        date_to = params.get("date_to")
        if date_to:
            qs = qs.filter(submitted_at__date__lte=date_to)

        ordering = params.get("ordering", "-submitted_at")
        if ordering in ("submitted_at", "-submitted_at", "amount", "-amount", "status"):
            qs = qs.order_by(ordering)
        return qs

    def get_permissions(self):
        if self.action == "create":
            return [IsWholesaler()]
        if self.action in ("verify", "flag", "dispute"):
            return [IsFinancialManager()]
        return super().get_permissions()

    def perform_create(self, serializer):
        # The Financial Manager notification is emitted by the payment_submitted
        # domain event (doc 4.11.2), so the view stays free of notify() calls.
        serializer.save(status=PaymentStatus.PENDING)

    # -- FR-FM-02 verification workflow ----------------------------------
    @action(detail=True, methods=["patch", "post"])
    def verify(self, request, pk=None):
        """PATCH /api/v1/payments/{id}/verify/ (TC-BE-11)."""
        record = self.get_object()
        if record.status == PaymentStatus.VERIFIED:
            raise ValidationError("Payment is already verified.")
        try:
            record.verify(request.user, notes=(request.data.get("notes") or ""))
        except ValueError as exc:
            raise ValidationError(str(exc))

        return Response({"success": True, "payment": PaymentRecordSerializer(record).data})

    @action(detail=True, methods=["patch", "post"])
    def flag(self, request, pk=None):
        """PATCH /api/v1/payments/{id}/flag/ — discrepancy identified."""
        record = self.get_object()
        reason = (request.data.get("reason") or "").strip()
        record.flag(reason)

        return Response({"success": True, "payment": PaymentRecordSerializer(record).data})

    @action(detail=True, methods=["patch", "post"])
    def dispute(self, request, pk=None):
        """PATCH /api/v1/payments/{id}/dispute/ — irreconcilable discrepancy."""
        record = self.get_object()
        reason = (request.data.get("reason") or "").strip()
        try:
            record.dispute(reason)
        except ValueError as exc:
            raise ValidationError(str(exc))

        return Response({"success": True, "payment": PaymentRecordSerializer(record).data})

    @action(detail=True, methods=["get"], url_path="receipt")
    def receipt(self, request, pk=None):
        """GET /api/v1/payments/{id}/receipt/ — audit receipt payload."""
        record = self.get_object()
        return Response({"success": True, "receipt": record.generate_receipt()})


class OrderViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """``/api/v1/orders/`` — procurement orders placed against farmer listings."""

    serializer_class = OrderSerializer
    queryset = Order.objects.none()  # only for schema lookup-type inference

    def get_queryset(self):
        user = self.request.user
        qs = Order.objects.select_related("wholesaler", "farmer", "product")
        if user.role in (Role.FINANCIAL_MANAGER, Role.SUPER_ADMIN, Role.USER_ADMIN):
            pass
        elif user.role == Role.WHOLESALER:
            qs = qs.filter(wholesaler=user)
        elif user.role == Role.FARMER:
            qs = qs.filter(farmer=user)
        else:
            qs = qs.none()

        status_param = self.request.query_params.get("status")
        if status_param and status_param != "ALL":
            qs = qs.filter(status=status_param)
        return qs

    def get_permissions(self):
        if self.action == "create":
            return [IsWholesaler()]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.validated_data["product"]

        if product.product_type != ProductType.FARMER_LISTING:
            raise ValidationError("Orders can only be placed against farmer listings.")
        if product.status != ProductStatus.ACTIVE:
            raise ValidationError("This listing is no longer active.")
        if product.owner == request.user:
            raise ValidationError("You cannot order your own listing.")

        with transaction.atomic():
            locked = Product.objects.select_for_update().get(pk=product.pk)
            if locked.status != ProductStatus.ACTIVE:
                raise ValidationError("This listing is no longer active.")
            quantity = serializer.validated_data["quantity"]
            if quantity > locked.quantity:
                raise ValidationError("Not enough quantity available.")

            order = serializer.save(
                wholesaler=request.user,
                farmer=locked.owner,
                reference=_generate_order_reference(),
                total_amount=quantity * locked.price_per_unit,
                status=OrderStatus.PROCESSING,
            )
            locked.quantity -= quantity
            if locked.quantity <= 0:
                locked.status = ProductStatus.SOLD
            locked.save(update_fields=["quantity", "status", "updated_at"])


        return Response(
            {"success": True, "order": OrderSerializer(order).data}, status=201
        )

    @action(detail=True, methods=["patch", "post"], url_path="status")
    def update_status(self, request, pk=None):
        """PATCH /api/v1/orders/{id}/status/ — advance the commercial lifecycle."""
        order = self.get_object()
        if request.user.role not in (Role.WHOLESALER, Role.FARMER, Role.SUPER_ADMIN):
            raise ValidationError("You cannot change this order's status.")
        if request.user.role == Role.WHOLESALER and order.wholesaler != request.user:
            raise ValidationError("You can only update your own orders.")
        if request.user.role == Role.FARMER and order.farmer != request.user:
            raise ValidationError("You can only update orders you received.")

        new_status = request.data.get("status")
        if not new_status:
            raise ValidationError({"status": "This field is required."})
        with transaction.atomic():
            try:
                order.set_status(new_status)
            except ValueError as exc:
                raise ValidationError(str(exc))

            if new_status == OrderStatus.CANCELLED:
                # Stock was reserved at order time, so give it back.
                locked = Product.objects.select_for_update().get(pk=order.product_id)
                locked.quantity += order.quantity
                if locked.status == ProductStatus.SOLD and locked.quantity > 0:
                    locked.status = ProductStatus.ACTIVE
                locked.save(update_fields=["quantity", "status", "updated_at"])

        return Response({"success": True, "order": OrderSerializer(order).data})
