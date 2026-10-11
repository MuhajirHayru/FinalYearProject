"""Payment management endpoints (doc 5.1.5, UC-04, FR-W-04, FR-FM-01..04)."""
import secrets
import uuid
from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import generics, mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from products.models import Product, ProductStatus, ProductType
from users.models import AuditLog, Role, User
from users.permissions import IsFinancialManager, IsWholesaler, IsAuthenticatedRole

from notifications.services import notify
from greenpath.privacy import contains_restricted_content
from .models import (
    AgreementStatus,
    BankAccount,
    BankAccountStatus,
    BusinessAgreement,
    FundingStatus,
    Order,
    OrderContactDisclosure,
    OrderPaymentStatus,
    OrderStatus,
    PayoutBank,
    PayoutStatus,
    PaymentRecord,
    PaymentStatus,
    Review,
    WalletFundingRequest,
    WalletPayoutRequest,
    WalletTransactionType,
    WalletTransaction,
)
from .serializers import (
    BusinessAgreementSerializer,
    FundingReviewDecisionSerializer,
    OrderSerializer,
    PaymentRecordSerializer,
    PayoutReviewDecisionSerializer,
    ReviewSerializer,
    WalletFundingRequestSerializer,
    WalletPayoutRequestSerializer,
    WalletSerializer,
    WalletTransactionSerializer,
)
from .wallet_services import (
    payout_reservation_is_active,
    release_escrow,
    release_order_reservation,
    reserve_order_funds,
    review_funding_request,
    review_payout_request,
    wallet_for,
)
from .chapa import (
    ChapaGatewayError,
    funding_from_webhook,
    initialize_checkout,
    validate_configuration,
    verify_funding,
    verify_webhook_signature,
)
from .serializers import BankAccountSerializer, ChapaFundingCreateSerializer, PayoutBankSerializer


def _generate_order_reference():
    """Collision-safe human-readable reference (no count()-based race)."""
    for _ in range(10):
        reference = f"#ORD{secrets.randbelow(900000) + 100000}"
        if not Order.objects.filter(reference=reference).exists():
            return reference
    return f"#ORD{secrets.token_hex(6).upper()}"


def _filter_financial_request_queryset(queryset, request, statuses, *, payout=False):
    params = request.query_params
    status = params.get("status", "").strip()
    valid_statuses = {value for value, _ in statuses}
    if status and status != "ALL":
        if status not in valid_statuses:
            raise ValidationError({"status": "Choose a valid request status."})
        queryset = queryset.filter(status=status)

    if request.user.role in (Role.FINANCIAL_MANAGER, Role.SUPER_ADMIN):
        role = params.get("role", "").strip()
        if role:
            if role not in (Role.FARMER, Role.WHOLESALER, Role.RETAILER):
                raise ValidationError({"role": "Choose a marketplace participant role."})
            queryset = queryset.filter(wallet__user__role=role)

    date_from = params.get("date_from", "").strip()
    date_to = params.get("date_to", "").strip()
    parsed_from = parse_date(date_from) if date_from else None
    parsed_to = parse_date(date_to) if date_to else None
    if date_from and parsed_from is None:
        raise ValidationError({"date_from": "Use YYYY-MM-DD."})
    if date_to and parsed_to is None:
        raise ValidationError({"date_to": "Use YYYY-MM-DD."})
    if parsed_from and parsed_to and parsed_from > parsed_to:
        raise ValidationError({"date_to": "Must be on or after date_from."})
    if parsed_from:
        queryset = queryset.filter(submitted_at__date__gte=parsed_from)
    if parsed_to:
        queryset = queryset.filter(submitted_at__date__lte=parsed_to)

    if payout:
        min_amount = params.get("min_amount", "").strip()
        max_amount = params.get("max_amount", "").strip()
        parsed_amounts = {}
        for field, value in (("min_amount", min_amount), ("max_amount", max_amount)):
            if value:
                try:
                    amount = Decimal(value)
                    if not amount.is_finite() or amount < 0:
                        raise InvalidOperation
                except (InvalidOperation, ValueError):
                    raise ValidationError({field: "Enter a valid amount."})
                parsed_amounts[field] = amount
                queryset = queryset.filter(
                    **{"amount__gte" if field == "min_amount" else "amount__lte": amount}
                )
        if (
            "min_amount" in parsed_amounts
            and "max_amount" in parsed_amounts
            and parsed_amounts["min_amount"] > parsed_amounts["max_amount"]
        ):
            raise ValidationError({"max_amount": "Must be greater than or equal to min_amount."})

        destination_type = params.get("method", "").strip()
        if destination_type == "REGISTERED":
            queryset = queryset.filter(payout_account__isnull=False)
        elif destination_type == "MANUAL":
            queryset = queryset.filter(payout_account__isnull=True)
        elif destination_type:
            raise ValidationError({"method": "Choose REGISTERED or MANUAL."})

    search = params.get("search", "").strip()
    if search:
        fields = (
            Q(wallet__user__full_name__icontains=search)
            | Q(external_reference__icontains=search)
        )
        if payout:
            fields |= Q(destination__icontains=search)
            try:
                fields |= Q(wallet__user__id=uuid.UUID(search))
            except ValueError:
                pass
            try:
                fields |= Q(id=uuid.UUID(search))
            except ValueError:
                pass
        else:
            fields |= Q(payment_method__icontains=search)
        queryset = queryset.filter(fields)

    ordering = params.get("ordering", "").strip()
    if payout:
        payout_ordering = {
            "newest": "-submitted_at",
            "oldest": "submitted_at",
            "amount_asc": "amount",
            "amount_desc": "-amount",
            "status": "status",
        }
        if ordering:
            if ordering not in payout_ordering:
                raise ValidationError({"ordering": "Choose a valid payout sort order."})
            queryset = queryset.order_by(payout_ordering[ordering], "-submitted_at")
    return queryset


class IsWalletParticipant(IsAuthenticatedRole):
    allowed_roles = (
        Role.FARMER,
        Role.WHOLESALER,
        Role.RETAILER,
        Role.FINANCIAL_MANAGER,
    )


class IsWalletDepositor(IsAuthenticatedRole):
    allowed_roles = (Role.WHOLESALER, Role.RETAILER)
    allow_super_admin = False


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
        qs = Order.objects.select_related(
            "wholesaler", "farmer", "retailer", "product"
        ).prefetch_related("agreement")
        if user.role in (Role.FINANCIAL_MANAGER, Role.SUPER_ADMIN, Role.USER_ADMIN):
            if user.role == Role.USER_ADMIN:
                from registrations.services import users_visible_to_admin

                visible_ids = users_visible_to_admin(user).values("pk")
                qs = qs.filter(
                    Q(wholesaler_id__in=visible_ids)
                    & (
                        Q(farmer_id__in=visible_ids)
                        | Q(farmer__isnull=True, retailer_id__in=visible_ids)
                    )
                )
        elif user.role == Role.WHOLESALER:
            qs = qs.filter(Q(wholesaler=user) | Q(farmer=user))
        elif user.role == Role.FARMER:
            qs = qs.filter(farmer=user)
        elif user.role == Role.RETAILER:
            qs = qs.filter(retailer=user)
        else:
            qs = qs.none()

        status_param = self.request.query_params.get("status")
        if status_param and status_param != "ALL":
            qs = qs.filter(status=status_param)
        return qs

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticatedRole((Role.WHOLESALER, Role.RETAILER))]
        if self.action == "release":
            return [IsFinancialManager()]
        if self.action == "disclose_contact":
            return [
                IsAuthenticatedRole(
                    (Role.USER_ADMIN, Role.FINANCIAL_MANAGER, Role.SUPER_ADMIN)
                )
            ]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        idempotency_key = (request.headers.get("Idempotency-Key") or "").strip()
        if idempotency_key:
            existing = Order.objects.filter(idempotency_key=idempotency_key).first()
            if existing is not None:
                if existing.buyer_id != request.user.id:
                    raise ValidationError("This idempotency key belongs to another order.")
                return Response(
                    {"success": True, "order": OrderSerializer(
                        existing, context=self.get_serializer_context()
                    ).data}
                )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.validated_data["product"]
        buyer_role = request.user.role
        expected_type = (
            ProductType.FARMER_LISTING
            if buyer_role == Role.WHOLESALER
            else ProductType.WHOLESALER_LISTING
        )
        expected_seller_role = (
            Role.FARMER if buyer_role == Role.WHOLESALER else Role.WHOLESALER
        )
        if product.product_type != expected_type:
            raise ValidationError(
                "This product is not available to your role for purchase."
            )
        if product.status != ProductStatus.ACTIVE:
            raise ValidationError("This listing is no longer active.")
        if product.owner == request.user:
            raise ValidationError("You cannot order your own listing.")

        if product.owner.role != expected_seller_role:
            raise ValidationError("The listing owner does not match the product type.")

        with transaction.atomic():
            locked = Product.objects.select_for_update().select_related("owner").get(
                pk=product.pk
            )
            if locked.status != ProductStatus.ACTIVE:
                raise ValidationError("This listing is no longer active.")
            quantity = serializer.validated_data["quantity"]
            if quantity > locked.quantity:
                raise ValidationError("Not enough quantity available.")
            order_total = quantity * locked.price_per_unit
            buyer_wallet = wallet_for(request.user, lock=True)
            if buyer_wallet.available_balance < order_total:
                shortfall = order_total - buyer_wallet.available_balance
                raise ValidationError(
                    {
                        "wallet": (
                            f"Insufficient available balance. Add at least "
                            f"{shortfall:.2f} ETB before placing this order."
                        )
                    }
                )

            order_data = {
                "reference": _generate_order_reference(),
                "wholesaler": (
                    request.user if buyer_role == Role.WHOLESALER else locked.owner
                ),
                "farmer": locked.owner if buyer_role == Role.WHOLESALER else None,
                "retailer": request.user if buyer_role == Role.RETAILER else None,
                "total_amount": order_total,
                "status": OrderStatus.PENDING_SELLER_APPROVAL,
                "payment_status": OrderPaymentStatus.RESERVED,
                "idempotency_key": idempotency_key,
                "delivery_information": (
                    request.data.get("delivery_information") or ""
                ).strip(),
            }
            if idempotency_key:
                order_data["idempotency_key"] = idempotency_key
            order = serializer.save(**order_data)
            reserve_order_funds(order, request.user)
            locked.quantity -= quantity
            if locked.quantity <= 0:
                locked.status = ProductStatus.SOLD
            locked.save(update_fields=["quantity", "status", "updated_at"])

        return Response(
            {
                "success": True,
                "order": OrderSerializer(order, context=self.get_serializer_context()).data,
            },
            status=201,
        )

    @action(detail=True, methods=["patch", "post"], url_path="status")
    def update_status(self, request, pk=None):
        """PATCH /api/v1/orders/{id}/status/ — advance the commercial lifecycle."""
        order = self.get_object()
        new_status = request.data.get("status")
        if not new_status:
            raise ValidationError({"status": "This field is required."})
        if new_status in (
            OrderStatus.AWAITING_PAYMENT_RELEASE,
            OrderStatus.COMPLETED,
            OrderStatus.DISPUTED,
        ):
            raise ValidationError(
                {"status": "Use the dedicated quality, dispute, or escrow action."}
            )
        with transaction.atomic():
            actor = request.user
            wallet_order = bool(order.payment_status)
            seller_transitions = (
                OrderStatus.ACCEPTED,
                OrderStatus.REJECTED,
                OrderStatus.PROCESSING,
                OrderStatus.CONFIRMED,
                OrderStatus.SHIPPED,
            )
            if wallet_order and new_status in seller_transitions and actor != order.seller:
                raise ValidationError("Only the seller can accept or advance this order.")
            if wallet_order and new_status == OrderStatus.CANCELLED and actor not in (
                order.buyer, order.seller
            ):
                raise ValidationError("Only the order participants can cancel this order.")
            if wallet_order and new_status in (
                OrderStatus.DELIVERED,
                OrderStatus.AWAITING_QUALITY_CONFIRMATION,
                OrderStatus.AWAITING_PAYMENT_RELEASE,
            ) and actor != order.buyer:
                raise ValidationError("Only the buyer can confirm delivery.")
            if actor not in (order.buyer, order.seller) and new_status not in (
                OrderStatus.CANCELLED,
                *seller_transitions,
                OrderStatus.DELIVERED,
                OrderStatus.AWAITING_QUALITY_CONFIRMATION,
                OrderStatus.AWAITING_PAYMENT_RELEASE,
            ):
                raise ValidationError("You are not a participant in this order.")
            if new_status == OrderStatus.ACCEPTED:
                if order.status != OrderStatus.PENDING_SELLER_APPROVAL:
                    raise ValidationError("Only a pending order can be accepted.")
                BusinessAgreement.objects.get_or_create(
                    order=order,
                    defaults={
                        "terms": (
                            f"{order.quantity} {order.product.unit_of_measure} of "
                            f"{order.product.title} at "
                            f"{order.product.price_per_unit} ETB per unit."
                        )
                    },
                )

            try:
                order.set_status(new_status)
            except ValueError as exc:
                raise ValidationError(str(exc))

            if new_status == OrderStatus.ACCEPTED:
                order.payment_status = OrderPaymentStatus.HELD
                order.save(update_fields=["payment_status", "updated_at"])
            if new_status in (OrderStatus.REJECTED, OrderStatus.CANCELLED):
                if order.payment_status == OrderPaymentStatus.HELD:
                    release_order_reservation(
                        order,
                        actor,
                        transaction_type=WalletTransactionType.RESERVATION_RELEASE,
                        description=f"Funds returned for {new_status.lower()} order "
                        f"{order.reference}",
                    )
                locked = Product.objects.select_for_update().get(pk=order.product_id)
                locked.quantity += order.quantity
                if locked.status == ProductStatus.SOLD and locked.quantity > 0:
                    locked.status = ProductStatus.ACTIVE
                locked.save(update_fields=["quantity", "status", "updated_at"])
                BusinessAgreement.objects.filter(order=order).update(
                    status=AgreementStatus.CANCELLED
                )
            elif new_status == OrderStatus.DELIVERED and order.payment_status:
                order.status = OrderStatus.AWAITING_QUALITY_CONFIRMATION
                order.delivered_at = timezone.now()
                order.save(update_fields=["status", "delivered_at", "updated_at"])
            elif new_status == OrderStatus.SHIPPED and order.payment_status:
                order.save(update_fields=["updated_at"])

        return Response(
            {
                "success": True,
                "order": OrderSerializer(order, context=self.get_serializer_context()).data,
            }
        )

    @action(detail=True, methods=["post"], url_path="confirm-quality")
    def confirm_quality(self, request, pk=None):
        order = self.get_object()
        if request.user != order.buyer:
            raise ValidationError("Only the buyer can confirm product quality.")
        if order.status != OrderStatus.AWAITING_QUALITY_CONFIRMATION:
            raise ValidationError("This order is not awaiting quality confirmation.")
        if order.payment_status != OrderPaymentStatus.HELD:
            raise ValidationError("There are no held funds to release for this order.")
        order.status = OrderStatus.AWAITING_PAYMENT_RELEASE
        order.payment_status = OrderPaymentStatus.RELEASE_PENDING
        order.quality_confirmed_at = timezone.now()
        order.save(
            update_fields=[
                "status", "payment_status", "quality_confirmed_at", "updated_at"
            ]
        )
        return Response(
            {
                "success": True,
                "order": OrderSerializer(order, context=self.get_serializer_context()).data,
            }
        )

    @action(detail=True, methods=["post"], url_path="dispute")
    def dispute(self, request, pk=None):
        order = self.get_object()
        if request.user != order.buyer:
            raise ValidationError("Only the buyer can report a quality dispute.")
        if order.status not in (
            OrderStatus.DELIVERED,
            OrderStatus.AWAITING_QUALITY_CONFIRMATION,
        ):
            raise ValidationError("A dispute can only be raised after delivery.")
        reason = (request.data.get("reason") or "").strip()
        if not reason:
            raise ValidationError({"reason": "A dispute reason is required."})
        order.status = OrderStatus.DISPUTED
        order.payment_status = OrderPaymentStatus.DISPUTED
        order.dispute_reason = reason
        order.save(
            update_fields=[
                "status", "payment_status", "dispute_reason", "updated_at"
            ]
        )
        BusinessAgreement.objects.filter(order=order).update(
            status=AgreementStatus.DISPUTED
        )
        return Response(
            {
                "success": True,
                "order": OrderSerializer(order, context=self.get_serializer_context()).data,
            }
        )

    @action(detail=True, methods=["post"], url_path="release")
    def release(self, request, pk=None):
        order = self.get_object()
        updated = release_escrow(
            order,
            request.user,
            external_reference=(
                request.data.get("external_reference") or ""
            ).strip(),
        )
        return Response(
            {
                "success": True,
                "order": OrderSerializer(
                    updated, context=self.get_serializer_context()
                ).data,
            }
        )

    @action(detail=True, methods=["post"], url_path="disclose-contact")
    def disclose_contact(self, request, pk=None):
        order = self.get_object()
        recipient_id = request.data.get("recipient_id")
        fields = request.data.get("fields")
        reason = (request.data.get("reason") or "").strip()
        allowed_fields = {
            "phone",
            "email",
            "address",
            "precise_location",
            "delivery_information",
        }
        if not isinstance(fields, list) or not fields:
            raise ValidationError({"fields": "Choose one or more fields to disclose."})
        if any(not isinstance(field, str) for field in fields):
            raise ValidationError({"fields": "Each field must be a string."})
        selected_fields = set(fields)
        if len(selected_fields) != len(fields) or not selected_fields <= allowed_fields:
            raise ValidationError({"fields": "Choose valid, non-duplicate fields."})
        if not reason or len(reason) > 500:
            raise ValidationError(
                {"reason": "Provide a reason of 1 to 500 characters."}
            )
        if contains_restricted_content(reason):
            raise ValidationError(
                {"reason": "Do not include private contact details in the reason."}
            )

        with transaction.atomic():
            locked_order = Order.objects.select_for_update().select_related(
                "wholesaler", "farmer", "retailer"
            ).get(pk=order.pk)
            if locked_order.status in (
                OrderStatus.PENDING_SELLER_APPROVAL,
                OrderStatus.REJECTED,
                OrderStatus.CANCELLED,
                OrderStatus.DISPUTED,
            ):
                raise ValidationError(
                    {"order": "Contact information cannot be disclosed at this stage."}
                )

            try:
                recipient = next(
                    participant
                    for participant in (locked_order.buyer, locked_order.seller)
                    if str(participant.pk) == str(recipient_id)
                )
            except StopIteration:
                raise ValidationError(
                    {"recipient_id": "Recipient must be an order participant."}
                )
            if recipient.pk == request.user.pk:
                raise ValidationError(
                    {"recipient_id": "Choose the other order participant."}
                )
            if "delivery_information" in selected_fields and (
                recipient.pk != locked_order.seller.pk
            ):
                raise ValidationError(
                    {
                        "fields": (
                            "Buyer delivery information may only be disclosed "
                            "to the seller."
                        )
                    }
                )

            if request.user.role == Role.USER_ADMIN:
                from registrations.services import users_visible_to_admin

                visible = users_visible_to_admin(request.user)
                if not all(
                    visible.filter(pk=participant.pk).exists()
                    for participant in (locked_order.buyer, locked_order.seller)
                ):
                    raise PermissionDenied(
                        "This order is outside your administrative scope."
                    )

            existing_fields = {
                field
                for disclosure in OrderContactDisclosure.objects.filter(
                    order=locked_order, recipient=recipient
                ).only("disclosed_fields")
                for field in disclosure.disclosed_fields
            }
            new_fields = selected_fields - existing_fields
            if not new_fields:
                raise ValidationError(
                    {"fields": "These fields have already been disclosed."}
                )

            contact = (
                locked_order.buyer
                if recipient.pk == locked_order.seller.pk
                else locked_order.seller
            )
            registration = getattr(contact, "registration", None)
            available_values = {
                "phone": contact.phone,
                "email": contact.email,
                "address": (
                    registration.business_address
                    if registration and registration.business_address
                    else contact.location
                ),
                "precise_location": (
                    bool(contact.latitude is not None and contact.longitude is not None)
                    or bool(contact.location)
                    or bool(
                        registration
                        and registration.business_address
                    )
                ),
                "delivery_information": locked_order.delivery_information,
            }
            empty_fields = {
                field for field in new_fields if not available_values[field]
            }
            if empty_fields:
                raise ValidationError(
                    {
                        "fields": (
                            "The selected information is not available for this "
                            "order participant."
                        )
                    }
                )

            disclosure = OrderContactDisclosure.objects.create(
                order=locked_order,
                recipient=recipient,
                authorized_by=request.user,
                disclosed_fields=sorted(new_fields),
                reason=reason,
            )
            AuditLog.objects.create(
                actor=request.user,
                action="order_contact_disclosed",
                target=locked_order.reference,
                detail=(
                    f"disclosure_id={disclosure.pk}; recipient_id={recipient.pk}; "
                    f"fields={','.join(disclosure.disclosed_fields)}; reason={reason}"
                ),
            )

        notify(
            user_ids=[recipient.pk],
            type="ORDER",
            message=(
                f"Authorized order information is now available for "
                f"{locked_order.reference}."
            ),
            actor=request.user,
            target_url=f"/orders/{locked_order.pk}",
        )
        updated = self.get_queryset().get(pk=locked_order.pk)
        return Response(
            {
                "success": True,
                "disclosure_id": str(disclosure.pk),
                "order": OrderSerializer(
                    updated, context=self.get_serializer_context()
                ).data,
            }
        )

    @action(detail=True, methods=["post"], url_path="resolve-dispute")
    def resolve_dispute(self, request, pk=None):
            if request.user.role not in (Role.FINANCIAL_MANAGER, Role.SUPER_ADMIN):
                raise ValidationError("Only financial staff can resolve payment disputes.")
            order = self.get_object()
            if order.status != OrderStatus.DISPUTED:
                raise ValidationError("This order has no open dispute.")
            decision = request.data.get("decision")
            if decision == "release":
                order.dispute_reason = ""
                order.status = OrderStatus.AWAITING_PAYMENT_RELEASE
                order.payment_status = OrderPaymentStatus.RELEASE_PENDING
                order.save(
                    update_fields=[
                        "dispute_reason", "status", "payment_status", "updated_at"
                    ]
                )
                updated = release_escrow(
                    order,
                    request.user,
                    external_reference=(request.data.get("external_reference") or "").strip(),
                )
            elif decision == "refund":
                with transaction.atomic():
                    order = Order.objects.select_for_update().get(pk=order.pk)
                    release_order_reservation(
                        order,
                        request.user,
                        transaction_type=WalletTransactionType.REFUND,
                        description=f"Dispute refund for order {order.reference}",
                    )
                    order.status = OrderStatus.CANCELLED
                    order.save(update_fields=["status", "updated_at"])
                    BusinessAgreement.objects.filter(order=order).update(
                        status=AgreementStatus.CANCELLED
                    )
                updated = order
            else:
                raise ValidationError({"decision": "Choose either 'release' or 'refund'."})
            return Response(
                {
                    "success": True,
                    "order": OrderSerializer(
                        updated, context=self.get_serializer_context()
                    ).data,
                }
            )


class WalletView(APIView):
    permission_classes = [IsWalletParticipant]
    serializer_class = WalletSerializer

    def get(self, request):
            wallet = wallet_for(request.user)
            return Response(WalletSerializer(wallet).data)


class WalletTransactionListView(generics.ListAPIView):
    serializer_class = WalletTransactionSerializer

    def get_queryset(self):
            user = self.request.user
            queryset = WalletTransaction.objects.select_related("wallet", "order")
            if user.role in (Role.FINANCIAL_MANAGER, Role.SUPER_ADMIN):
                pass
            else:
                queryset = queryset.filter(wallet__user=user)
            kind = self.request.query_params.get("type")
            if kind:
                queryset = queryset.filter(transaction_type=kind)
            date_from = self.request.query_params.get("date_from")
            if date_from:
                queryset = queryset.filter(created_at__date__gte=date_from)
            date_to = self.request.query_params.get("date_to")
            if date_to:
                queryset = queryset.filter(created_at__date__lte=date_to)
            return queryset


class WalletFundingRequestListCreateView(generics.ListCreateAPIView):
    serializer_class = WalletFundingRequestSerializer

    def get_queryset(self):
            queryset = WalletFundingRequest.objects.select_related("wallet__user")
            if self.request.user.role not in (Role.FINANCIAL_MANAGER, Role.SUPER_ADMIN):
                queryset = queryset.filter(wallet__user=self.request.user)
            return _filter_financial_request_queryset(
                queryset, self.request, FundingStatus.choices
            )

    def perform_create(self, serializer):
            if self.request.user.role not in (
                Role.FARMER,
                Role.WHOLESALER,
                Role.RETAILER,
            ):
                raise ValidationError("Only marketplace participants can request funding.")
            serializer.save(wallet=wallet_for(self.request.user))

    def create(self, request, *args, **kwargs):
            existing = WalletFundingRequest.objects.filter(
                wallet__user=request.user,
                payment_method=request.data.get("payment_method"),
                external_reference=(request.data.get("external_reference") or "").strip(),
            ).first()
            if existing:
                amount = request.data.get("amount")
                if str(existing.amount) != str(amount):
                    raise ValidationError(
                        {"external_reference": "This transfer reference is already submitted."}
                    )
                return Response(
                    WalletFundingRequestSerializer(existing).data,
                    status=200,
                )
            response = super().create(request, *args, **kwargs)
            if response.status_code == 201:
                notify(
                    roles=(Role.FINANCIAL_MANAGER, Role.SUPER_ADMIN),
                    type="PAYMENT",
                    message=f"Wallet funding request received from {request.user.full_name}.",
                    actor=request.user,
                    target_url="/financial-manager/payments?tab=funding",
                )
            return response


class ChapaFundingInitializeView(APIView):
    permission_classes = [IsWalletDepositor]
    serializer_class = ChapaFundingCreateSerializer

    def post(self, request):
        validate_configuration()
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        amount = serializer.validated_data["amount"]
        idempotency_key = (request.headers.get("Idempotency-Key") or "").strip()
        if len(idempotency_key) > 100:
            raise ValidationError(
                {"Idempotency-Key": "Must be 100 characters or fewer."}
            )
        if idempotency_key:
            existing = WalletFundingRequest.objects.filter(
                idempotency_key=idempotency_key
            ).first()
            if existing:
                if existing.wallet.user_id != request.user.id:
                    raise ValidationError(
                        "This idempotency key belongs to another deposit."
                    )
                if existing.amount != amount:
                    raise ValidationError(
                        {"amount": "This idempotency key was used for another amount."}
                    )
                return Response(WalletFundingRequestSerializer(existing).data)

        wallet = wallet_for(request.user)
        funding = WalletFundingRequest.objects.create(
            wallet=wallet,
            amount=amount,
            payment_method="Chapa",
            external_reference=f"GP{uuid.uuid4().hex.upper()}",
            status=FundingStatus.AWAITING_PAYMENT,
            payment_mode="TEST",
            idempotency_key=idempotency_key,
        )
        try:
            checkout_url = initialize_checkout(funding)
        except ChapaGatewayError as exc:
            provider_http_status = getattr(exc.__cause__, "code", None)
            if isinstance(provider_http_status, int) and 400 <= provider_http_status < 500:
                funding.status = FundingStatus.FAILED
                funding.provider_status = (
                    f"INITIALIZATION_REJECTED_{provider_http_status}"
                )
            else:
                funding.status = FundingStatus.PAYMENT_VERIFICATION_PENDING
                funding.provider_status = "INITIALIZATION_UNCONFIRMED"
            funding.save(update_fields=["status", "provider_status"])
            raise
        funding.checkout_url = checkout_url
        funding.save(update_fields=["checkout_url"])
        return Response(WalletFundingRequestSerializer(funding).data, status=201)


class ChapaFundingVerifyView(APIView):
    permission_classes = [IsWalletParticipant]
    serializer_class = WalletFundingRequestSerializer

    def post(self, request, pk):
        funding = get_object_or_404(
            WalletFundingRequest.objects.select_related("wallet__user"),
            pk=pk,
            payment_method="Chapa",
            payment_mode="TEST",
        )
        if funding.wallet.user_id != request.user.id and request.user.role not in (
            Role.FINANCIAL_MANAGER,
            Role.SUPER_ADMIN,
        ):
            raise ValidationError("You cannot verify another user's deposit.")
        funding, became_eligible = verify_funding(funding)
        if became_eligible:
            notify(
                roles=(Role.FINANCIAL_MANAGER, Role.SUPER_ADMIN),
                type="PAYMENT",
                message=(
                    f"Chapa verified a wallet deposit from "
                    f"{funding.wallet.user.full_name}; it awaits financial approval."
                ),
                actor=funding.wallet.user,
                target_url="/financial-manager/payments?tab=funding",
            )
        return Response(WalletFundingRequestSerializer(funding).data)


class PayoutBankListView(generics.ListAPIView):
    serializer_class = PayoutBankSerializer
    permission_classes = [IsAuthenticatedRole]

    def get_permissions(self):
        return [IsAuthenticatedRole(
            (Role.FARMER, Role.WHOLESALER, Role.RETAILER, Role.FINANCIAL_MANAGER)
        )]

    def get_queryset(self):
        queryset = PayoutBank.objects.filter(is_active=True)
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset


class BankAccountListCreateView(generics.ListCreateAPIView):
    serializer_class = BankAccountSerializer

    def get_permissions(self):
        return [IsAuthenticatedRole(
            (Role.FARMER, Role.WHOLESALER, Role.RETAILER, Role.FINANCIAL_MANAGER)
        )]

    def get_queryset(self):
        queryset = BankAccount.objects.select_related("user", "bank").prefetch_related(
            "payout_requests"
        )
        if self.request.user.role in (Role.FINANCIAL_MANAGER, Role.SUPER_ADMIN):
            search = self.request.query_params.get("search", "").strip()
            role = self.request.query_params.get("role", "").strip()
            bank = self.request.query_params.get("bank", "").strip()
            status = self.request.query_params.get("status", "").strip()
            if search:
                queryset = queryset.filter(
                    Q(user__full_name__icontains=search)
                    | Q(user__email__icontains=search)
                    | Q(account_holder_name__icontains=search)
                )
            if role in (Role.FARMER, Role.WHOLESALER, Role.RETAILER):
                queryset = queryset.filter(user__role=role)
            if bank:
                queryset = queryset.filter(bank__code=bank)
            if status in BankAccountStatus.values:
                queryset = queryset.filter(status=status)
            return queryset.filter(
                user__role__in=(Role.FARMER, Role.WHOLESALER, Role.RETAILER)
            )
        return queryset.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        if request.user.role not in (Role.FARMER, Role.WHOLESALER, Role.RETAILER):
            raise ValidationError("Only marketplace users can register payout accounts.")
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        with transaction.atomic():
            User.objects.select_for_update().get(pk=self.request.user.pk)
            if serializer.validated_data.get("is_default"):
                BankAccount.objects.filter(user=self.request.user).update(is_default=False)
            account = serializer.save(user=self.request.user)
            AuditLog.objects.create(
                actor=self.request.user,
                action="payout_account_registered",
                target=str(account.pk),
                detail=f"Registered payout account at {account.bank.name}.",
            )


class BankAccountDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = BankAccountSerializer
    lookup_url_kwarg = "pk"
    http_method_names = ["get", "put", "patch", "delete", "head", "options"]

    def get_permissions(self):
        return [IsAuthenticatedRole(
            (Role.FARMER, Role.WHOLESALER, Role.RETAILER, Role.FINANCIAL_MANAGER)
        )]

    def get_queryset(self):
        queryset = BankAccount.objects.select_related("user", "bank").prefetch_related(
            "payout_requests"
        )
        if self.request.user.role in (Role.FINANCIAL_MANAGER, Role.SUPER_ADMIN):
            return queryset.filter(
                user__role__in=(Role.FARMER, Role.WHOLESALER, Role.RETAILER)
            )
        return queryset.filter(user=self.request.user)

    def _reject_if_payout_pending(self, account):
        if account.payout_requests.filter(status="PENDING").exists():
            raise ValidationError(
                {"bank_account": "This account cannot be changed while a payout is under review."}
            )

    def perform_update(self, serializer):
        account = self.get_object()
        if account.user_id != self.request.user.id:
            raise ValidationError("Financial staff may view accounts but cannot edit them.")
        with transaction.atomic():
            User.objects.select_for_update().get(pk=account.user_id)
            account = BankAccount.objects.select_for_update().get(pk=account.pk)
            self._reject_if_payout_pending(account)
            if serializer.validated_data.get("is_default"):
                BankAccount.objects.filter(user_id=account.user_id).exclude(
                    pk=account.pk
                ).update(is_default=False)
            serializer.instance = account
            account = serializer.save()
            AuditLog.objects.create(
                actor=self.request.user,
                action="payout_account_updated",
                target=str(account.pk),
                detail=f"Updated payout account at {account.bank.name}.",
            )

    def perform_destroy(self, instance):
        if instance.user_id != self.request.user.id:
            raise ValidationError("Financial staff may view accounts but cannot delete them.")
        with transaction.atomic():
            User.objects.select_for_update().get(pk=instance.user_id)
            instance = BankAccount.objects.select_for_update().get(pk=instance.pk)
            self._reject_if_payout_pending(instance)
            was_default = instance.is_default
            owner_id = instance.user_id
            account_id = str(instance.pk)
            instance.delete()
            if was_default:
                replacement = BankAccount.objects.filter(user_id=owner_id).first()
                if replacement:
                    replacement.is_default = True
                    replacement.save(update_fields=["is_default", "updated_at"])
            AuditLog.objects.create(
                actor=self.request.user,
                action="payout_account_removed",
                target=account_id,
                detail="Removed payout account.",
            )


class BankAccountFullDetailsView(APIView):
    permission_classes = [IsFinancialManager]

    def get(self, request, pk):
        from .bank_accounts import decrypt_account_number

        account = get_object_or_404(BankAccount.objects.select_related("user", "bank"), pk=pk)
        with transaction.atomic():
            AuditLog.objects.create(
                actor=request.user,
                action="payout_account_sensitive_view",
                target=str(account.pk),
                detail=f"Financial Manager viewed full payout details for user {account.user_id}.",
            )
        return Response(
            {
                **BankAccountSerializer(account).data,
                "account_number": decrypt_account_number(
                    account.account_number_encrypted
                ),
            }
        )


class BankAccountReviewFlagView(APIView):
    permission_classes = [IsFinancialManager]

    def post(self, request, pk):
        notes = (request.data.get("notes") or "").strip()
        if not notes:
            raise ValidationError({"notes": "Provide a reason for requesting further review."})
        with transaction.atomic():
            account = get_object_or_404(
                BankAccount.objects.select_for_update().select_related("user", "bank"),
                pk=pk,
            )
            if account.status == BankAccountStatus.REQUIRES_REVIEW:
                raise ValidationError({"status": "This account already requires further review."})
            account.status = BankAccountStatus.REQUIRES_REVIEW
            account.save(update_fields=["status", "updated_at"])
            AuditLog.objects.create(
                actor=request.user,
                action="payout_account_review_requested",
                target=str(account.pk),
                detail=notes,
            )
        notify(
            user_ids=[account.user_id],
            type="PAYMENT",
            message="A Financial Manager requested further review of your payout account.",
            actor=request.user,
            target_url="/settings#bank-accounts",
        )
        return Response(BankAccountSerializer(account).data)


class ChapaWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        body = request.body
        if not verify_webhook_signature(
            body,
            request.headers.get("x-chapa-signature", ""),
            request.headers.get("x-chapa-signature-v2", ""),
        ):
            return Response({"detail": "Invalid Chapa webhook signature."}, status=403)
        funding = funding_from_webhook(body)
        if funding is None:
            return Response({"detail": "Unknown Chapa transaction reference."}, status=404)
        _, became_eligible = verify_funding(funding)
        if became_eligible:
            notify(
                roles=(Role.FINANCIAL_MANAGER, Role.SUPER_ADMIN),
                type="PAYMENT",
                message=(
                    f"Chapa verified a wallet deposit from "
                    f"{funding.wallet.user.full_name}; it awaits financial approval."
                ),
                actor=funding.wallet.user,
                target_url="/financial-manager/payments?tab=funding",
            )
        return Response({"success": True})


class WalletFundingReviewView(APIView):
    permission_classes = [IsFinancialManager]
    serializer_class = FundingReviewDecisionSerializer

    @extend_schema(
        request=FundingReviewDecisionSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    def post(self, request, pk):
            decision = self.serializer_class(data=request.data)
            decision.is_valid(raise_exception=True)
            approve = decision.validated_data["approve"]
            funding = review_funding_request(
                pk,
                request.user,
                approve=approve,
                notes=decision.validated_data["notes"],
            )
            notify(
                user_ids=[funding.wallet.user_id],
                type="PAYMENT",
                message=(
                    f"Your wallet funding request was "
                    f"{'verified' if approve else 'rejected'}."
                ),
                actor=request.user,
                target_url="/wallet",
            )
            return Response(
                {"success": True, "funding_request": WalletFundingRequestSerializer(funding).data}
            )


class WalletPayoutRequestListCreateView(generics.ListCreateAPIView):
    serializer_class = WalletPayoutRequestSerializer

    def get_queryset(self):
        queryset = WalletPayoutRequest.objects.select_related(
            "wallet__user", "payout_account__bank"
        )
        if self.request.user.role not in (Role.FINANCIAL_MANAGER, Role.SUPER_ADMIN):
            queryset = queryset.filter(wallet__user=self.request.user)
        return _filter_financial_request_queryset(
            queryset, self.request, PayoutStatus.choices, payout=True
        )

    def create(self, request, *args, **kwargs):
        idempotency_key = (request.headers.get("Idempotency-Key") or "").strip()
        if idempotency_key:
            existing = WalletPayoutRequest.objects.filter(
                idempotency_key=idempotency_key
            ).first()
            if existing:
                if existing.wallet.user_id != request.user.id:
                    raise ValidationError("This idempotency key belongs to another request.")
                return Response(
                    WalletPayoutRequestSerializer(
                        existing, context=self.get_serializer_context()
                    ).data
                )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if request.user.role not in (Role.FARMER, Role.WHOLESALER, Role.RETAILER):
            raise ValidationError("Only marketplace participants can request a payout.")
        created = False
        with transaction.atomic():
            payout_account = serializer.validated_data.get("payout_account")
            if payout_account:
                payout_account = BankAccount.objects.select_for_update().get(
                    pk=payout_account.pk, user=request.user
                )
            wallet = wallet_for(request.user, lock=True)
            payout = None
            if idempotency_key:
                payout = (
                    WalletPayoutRequest.objects.select_related(
                        "wallet__user", "payout_account__bank"
                    )
                    .filter(idempotency_key=idempotency_key)
                    .first()
                )
                if payout and payout.wallet.user_id != request.user.id:
                    raise ValidationError(
                        "This idempotency key belongs to another request."
                    )

            if payout is None:
                amount = serializer.validated_data["amount"]
                if wallet.available_balance < amount:
                    raise ValidationError(
                        {"wallet": "Insufficient available balance."}
                    )
                wallet.available_balance -= amount
                wallet.held_balance += amount
                wallet.save(
                    update_fields=["available_balance", "held_balance", "updated_at"]
                )
                payout = serializer.save(
                    wallet=wallet,
                    idempotency_key=idempotency_key,
                )
                WalletTransaction.objects.create(
                    wallet=wallet,
                    transaction_type=WalletTransactionType.PAYOUT_RESERVATION,
                    amount=amount,
                    available_delta=-amount,
                    held_delta=amount,
                    reference=f"PAYOUT-HOLD-{payout.pk}",
                    actor=request.user,
                    description="Funds reserved for manual payout review",
                )
                AuditLog.objects.create(
                    actor=request.user,
                    action="wallet_payout_requested",
                    target=str(payout.pk),
                    detail=(
                        f"Status: none -> {PayoutStatus.PENDING}; "
                        f"amount: {amount:.2f} ETB."
                    ),
                )
                created = True
        if created:
            notify(
                roles=(Role.FINANCIAL_MANAGER, Role.SUPER_ADMIN),
                type="PAYMENT",
                message=f"Payout request received from {request.user.full_name}.",
                actor=request.user,
                target_url="/financial-manager/payouts",
            )
        return Response(
            WalletPayoutRequestSerializer(
                payout, context=self.get_serializer_context()
            ).data,
            status=201 if created else 200,
        )


class WalletPayoutDetailView(APIView):
    permission_classes = [IsFinancialManager]

    def get(self, request, pk):
        payout = get_object_or_404(
            WalletPayoutRequest.objects.select_related(
                "wallet__user",
                "payout_account__bank",
                "reviewed_by",
            ),
            pk=pk,
        )
        wallet = payout.wallet
        transactions = WalletTransaction.objects.filter(
            wallet=wallet,
            reference__in=(
                f"PAYOUT-HOLD-{payout.pk}",
                f"PAYOUT-{payout.pk}",
                f"PAYOUT-RETURN-{payout.pk}",
            ),
        ).select_related("actor").order_by("created_at")
        history = AuditLog.objects.filter(target=str(payout.pk)).select_related(
            "actor"
        ).order_by("created_at")
        reserved = (
            wallet.held_balance >= payout.amount
            and payout_reservation_is_active(payout)
        )
        account = payout.payout_account
        return Response(
            {
                "payout": WalletPayoutRequestSerializer(
                    payout, context={"request": request}
                ).data,
                "requester": {
                    "id": str(wallet.user_id),
                    "name": wallet.user.full_name,
                    "role": wallet.user.role,
                    "email": wallet.user.email,
                },
                "wallet": {
                    "currency": wallet.currency,
                    "available_balance": wallet.available_balance,
                    "held_balance": wallet.held_balance,
                    "requested_amount_reserved": reserved,
                },
                "destination_review": {
                    "status": account.status if account else "MANUAL_DESTINATION",
                    "bank_name": account.bank.name if account else "",
                    "account_holder_name": account.account_holder_name if account else "",
                    "account_type": account.account_type if account else "",
                    "masked_account_number": (
                        account.masked_account_number if account else ""
                    ),
                    "requires_external_confirmation": True,
                },
                "eligible_for_manual_confirmation": (
                    payout.status == PayoutStatus.PENDING
                    and payout.amount > 0
                    and reserved
                    and bool(payout.destination.strip())
                ),
                "transactions": [
                    {
                        "id": str(item.pk),
                        "type": item.transaction_type,
                        "amount": item.amount,
                        "reference": item.reference,
                        "external_reference": item.external_reference,
                        "description": item.description,
                        "actor": item.actor.full_name if item.actor else "",
                        "created_at": item.created_at,
                    }
                    for item in transactions
                ],
                "history": [
                    {
                        "actor": item.actor.full_name if item.actor else "",
                        "action": item.action,
                        "detail": item.detail,
                        "created_at": item.created_at,
                    }
                    for item in history
                ],
            }
        )


class WalletPayoutReviewView(APIView):
    permission_classes = [IsFinancialManager]
    serializer_class = PayoutReviewDecisionSerializer

    @extend_schema(
        request=PayoutReviewDecisionSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    def post(self, request, pk):
        decision = self.serializer_class(data=request.data)
        decision.is_valid(raise_exception=True)
        approve = decision.validated_data["approve"]
        payout = review_payout_request(
            pk,
            request.user,
            approve=approve,
            external_reference=decision.validated_data["external_reference"],
            notes=decision.validated_data["notes"],
        )
        status_message = (
            "confirmed as paid after manual transfer verification"
            if approve
            else f"rejected: {payout.review_notes.strip()}"
        )
        notify(
            user_ids=[payout.wallet.user_id],
            type="PAYMENT",
            message=f"Your payout request was {status_message}.",
            actor=request.user,
            target_url="/wallet",
        )
        return Response(
            {
                "success": True,
                "payout_request": WalletPayoutRequestSerializer(
                    payout, context={"request": request}
                ).data,
            }
        )


class BusinessAgreementListView(generics.ListAPIView):
    serializer_class = BusinessAgreementSerializer

    def get_queryset(self):
            user = self.request.user
            queryset = BusinessAgreement.objects.select_related(
                "order__wholesaler", "order__farmer", "order__retailer", "order__product"
            )
            if user.role in (Role.FINANCIAL_MANAGER, Role.SUPER_ADMIN):
                return queryset
            return queryset.filter(
                Q(order__wholesaler=user) | Q(order__farmer=user) | Q(order__retailer=user)
            )


class ReviewListCreateView(generics.ListCreateAPIView):
    serializer_class = ReviewSerializer

    def get_queryset(self):
            user = self.request.user
            queryset = Review.objects.select_related("reviewer", "reviewee", "order")
            target_id = self.request.query_params.get("user")
            if target_id:
                return queryset.filter(reviewee_id=target_id)
            return queryset.filter(Q(reviewer=user) | Q(reviewee=user))

    def create(self, request, *args, **kwargs):
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            order = get_object_or_404(Order.objects.select_related(
                "wholesaler", "farmer", "retailer"
            ), pk=serializer.validated_data["order"].pk)
            actor = request.user
            if order.status != OrderStatus.COMPLETED:
                raise ValidationError("Reviews are available after the order is completed.")
            if actor == order.buyer:
                reviewee = order.seller
            elif actor == order.seller:
                reviewee = order.buyer
            else:
                raise ValidationError("Only participants in this order can write a review.")
            if Review.objects.filter(order=order, reviewer=actor, reviewee=reviewee).exists():
                raise ValidationError("You have already reviewed this transaction.")
            review = serializer.save(reviewer=actor, reviewee=reviewee)
            notify(
                user_ids=[reviewee.id],
                type="SYSTEM",
                message=f"You received a {review.rating}-star transaction review.",
                actor=actor,
                target_url="/reviews",
            )
            return Response(ReviewSerializer(review).data, status=201)
