"""Atomic wallet movements for manually verified funding and escrow."""

import secrets
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from users.models import AuditLog

from .models import (
    AgreementStatus,
    BusinessAgreement,
    FundingStatus,
    Order,
    OrderPaymentStatus,
    OrderStatus,
    PayoutStatus,
    Wallet,
    WalletFundingRequest,
    WalletPayoutRequest,
    WalletTransaction,
    WalletTransactionType,
)


def transaction_reference(prefix):
    return f"{prefix}-{secrets.token_hex(12).upper()}"


def wallet_for(user, *, lock=False):
    wallet, _ = Wallet.objects.get_or_create(user=user)
    if lock:
        return Wallet.objects.select_for_update().get(pk=wallet.pk)
    return wallet


def reserve_order_funds(order, actor):
    """Move order funds from spendable to held balance exactly once."""
    wallet = wallet_for(order.buyer, lock=True)
    amount = order.total_amount
    if wallet.available_balance < amount:
        shortfall = amount - wallet.available_balance
        raise ValidationError(
            {
                "wallet": (
                    f"Insufficient available balance. Add at least "
                    f"{shortfall:.2f} ETB before placing this order."
                )
            }
        )
    wallet.available_balance -= amount
    wallet.held_balance += amount
    wallet.save(update_fields=["available_balance", "held_balance", "updated_at"])
    WalletTransaction.objects.create(
        wallet=wallet,
        order=order,
        transaction_type=WalletTransactionType.ORDER_RESERVATION,
        amount=amount,
        available_delta=-amount,
        held_delta=amount,
        reference=transaction_reference("ORDER-HOLD"),
        actor=actor,
        description=f"Escrow held for order {order.reference}",
    )
    order.payment_status = OrderPaymentStatus.HELD
    order.save(update_fields=["payment_status", "updated_at"])


@transaction.atomic
def release_order_reservation(order, actor, *, transaction_type, description):
    wallet = Wallet.objects.select_for_update().get(user=order.buyer)
    amount = order.total_amount
    if wallet.held_balance < amount:
        raise ValidationError({"wallet": "Held order funds are not available."})
    wallet.held_balance -= amount
    wallet.available_balance += amount
    wallet.save(update_fields=["held_balance", "available_balance", "updated_at"])
    WalletTransaction.objects.create(
        wallet=wallet,
        order=order,
        transaction_type=transaction_type,
        amount=amount,
        available_delta=amount,
        held_delta=-amount,
        reference=transaction_reference("ORDER-RETURN"),
        actor=actor,
        description=description,
    )
    order.payment_status = OrderPaymentStatus.REFUNDED
    order.save(update_fields=["payment_status", "updated_at"])


@transaction.atomic
def release_escrow(order, financial_manager, external_reference=""):
    """Pay an approved escrow into the seller's platform wallet once."""
    locked_order = Order.objects.select_for_update().select_related(
        "wholesaler", "farmer", "retailer"
    ).get(pk=order.pk)
    if locked_order.status != OrderStatus.AWAITING_PAYMENT_RELEASE:
        raise ValidationError(
            {"order": "Only quality-confirmed orders can be released."}
        )
    if locked_order.payment_status != OrderPaymentStatus.RELEASE_PENDING:
        raise ValidationError({"payment": "This payment is not awaiting release."})
    if locked_order.dispute_reason:
        raise ValidationError({"order": "A disputed order cannot be released."})

    buyer_wallet = Wallet.objects.select_for_update().get(user=locked_order.buyer)
    amount = locked_order.total_amount
    if buyer_wallet.held_balance < amount:
        raise ValidationError({"wallet": "Held escrow funds do not cover this order."})
    seller_wallet = wallet_for(locked_order.seller, lock=True)
    buyer_wallet.held_balance -= amount
    buyer_wallet.save(update_fields=["held_balance", "updated_at"])
    seller_wallet.available_balance += amount
    seller_wallet.save(update_fields=["available_balance", "updated_at"])

    WalletTransaction.objects.create(
        wallet=buyer_wallet,
        order=locked_order,
        transaction_type=WalletTransactionType.ESCROW_RELEASE,
        amount=amount,
        held_delta=-amount,
        reference=transaction_reference("ESCROW-OUT"),
        external_reference=external_reference,
        actor=financial_manager,
        description=f"Escrow released for order {locked_order.reference}",
    )
    WalletTransaction.objects.create(
        wallet=seller_wallet,
        order=locked_order,
        transaction_type=WalletTransactionType.ESCROW_RELEASE,
        amount=amount,
        available_delta=amount,
        reference=transaction_reference("ESCROW-IN"),
        external_reference=external_reference,
        actor=financial_manager,
        description=f"Escrow received for order {locked_order.reference}",
    )
    locked_order.payment_status = OrderPaymentStatus.RELEASED
    locked_order.status = OrderStatus.COMPLETED
    locked_order.save(update_fields=["payment_status", "status", "updated_at"])
    BusinessAgreement.objects.filter(order=locked_order).update(
        status=AgreementStatus.COMPLETED,
        completed_at=timezone.now(),
    )
    AuditLog.objects.create(
        actor=financial_manager,
        action="escrow_released",
        target=locked_order.reference,
        detail=f"Released {amount:.2f} ETB; external settlement ref: {external_reference}",
    )
    return locked_order


@transaction.atomic
def review_funding_request(request_id, financial_manager, *, approve, notes=""):
    funding = WalletFundingRequest.objects.select_for_update().select_related(
        "wallet__user"
    ).get(pk=request_id)
    if funding.status not in (
        FundingStatus.PENDING,
        FundingStatus.AWAITING_APPROVAL,
    ):
        raise ValidationError({"status": "This funding request has already been reviewed."})
    if funding.payment_method == "Chapa" and approve:
        if not (
            funding.payment_mode == "TEST"
            and funding.payment_verified
            and funding.verified_amount == funding.amount
            and funding.verified_currency == funding.wallet.currency.upper()
            and funding.provider_status.lower() == "success"
        ):
            raise ValidationError(
                {"payment": "Chapa has not independently verified this deposit."}
            )
    funding.reviewed_at = timezone.now()
    funding.reviewed_by = financial_manager
    funding.review_notes = notes.strip()
    if approve:
        wallet = Wallet.objects.select_for_update().get(pk=funding.wallet_id)
        wallet.available_balance += funding.amount
        wallet.save(update_fields=["available_balance", "updated_at"])
        funding.status = (
            FundingStatus.APPROVED
            if funding.payment_method == "Chapa"
            else FundingStatus.VERIFIED
        )
        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type=WalletTransactionType.FUNDING,
            amount=funding.amount,
            available_delta=funding.amount,
            reference=f"FUNDING-{funding.pk}",
            external_reference=funding.external_reference,
            actor=financial_manager,
            description=(
                "Financially approved Chapa test-mode deposit"
                if funding.payment_method == "Chapa"
                else "Manually verified wallet funding"
            ),
        )
    else:
        funding.status = FundingStatus.REJECTED
    funding.save(
        update_fields=["status", "reviewed_at", "reviewed_by", "review_notes"]
    )
    AuditLog.objects.create(
        actor=financial_manager,
        action=(
            "wallet_funding_approved"
            if approve and funding.payment_method == "Chapa"
            else "wallet_funding_verified"
            if approve
            else "wallet_funding_rejected"
        ),
        target=str(funding.pk),
        detail=f"{funding.amount:.2f} ETB; {funding.external_reference}; {notes.strip()}",
    )
    return funding


@transaction.atomic
def review_payout_request(
    request_id, financial_manager, *, approve, external_reference="", notes=""
):
    payout = WalletPayoutRequest.objects.select_for_update().select_related(
        "wallet__user"
    ).get(pk=request_id)
    if payout.status != PayoutStatus.PENDING:
        raise ValidationError({"status": "This payout request has already been reviewed."})
    wallet = Wallet.objects.select_for_update().get(pk=payout.wallet_id)
    if approve:
        external_reference = external_reference.strip()
        if not external_reference:
            raise ValidationError(
                {"external_reference": "Enter the verified bank or transfer reference."}
            )
        if wallet.held_balance < payout.amount:
            raise ValidationError({"wallet": "Held payout funds are not available."})
        wallet.held_balance -= payout.amount
        wallet.save(update_fields=["held_balance", "updated_at"])
        payout.status = PayoutStatus.PAID
        payout.external_reference = external_reference
        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type=WalletTransactionType.PAYOUT,
            amount=payout.amount,
            held_delta=-payout.amount,
            reference=f"PAYOUT-{payout.pk}",
            external_reference=external_reference,
            actor=financial_manager,
            description="Manually settled wallet payout",
        )
    else:
        wallet.held_balance -= payout.amount
        wallet.available_balance += payout.amount
        wallet.save(
            update_fields=["held_balance", "available_balance", "updated_at"]
        )
        payout.status = PayoutStatus.REJECTED
        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type=WalletTransactionType.RESERVATION_RELEASE,
            amount=payout.amount,
            available_delta=payout.amount,
            held_delta=-payout.amount,
            reference=f"PAYOUT-RETURN-{payout.pk}",
            actor=financial_manager,
            description="Rejected payout returned to available balance",
        )
    payout.reviewed_at = timezone.now()
    payout.reviewed_by = financial_manager
    payout.review_notes = notes.strip()
    payout.save(
        update_fields=[
            "status", "reviewed_at", "reviewed_by", "external_reference",
            "review_notes",
        ]
    )
    AuditLog.objects.create(
        actor=financial_manager,
        action="wallet_payout_paid" if approve else "wallet_payout_rejected",
        target=str(payout.pk),
        detail=f"{payout.amount:.2f} ETB; {external_reference}; {notes.strip()}",
    )
    return payout
