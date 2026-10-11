from decimal import Decimal

import pytest

from payments.models import (
    PayoutStatus,
    Wallet,
    WalletPayoutRequest,
    WalletTransaction,
)
from notifications.models import Notification
from users.models import AuditLog, Role

pytestmark = pytest.mark.django_db


def payout_for(user, *, amount, destination, status=PayoutStatus.PENDING):
    amount = Decimal(amount)
    wallet, _ = Wallet.objects.get_or_create(
        user=user, defaults={"available_balance": Decimal("1000.00")}
    )
    if status == PayoutStatus.PENDING:
        wallet.available_balance = max(wallet.available_balance, amount)
    payout = WalletPayoutRequest.objects.create(
        wallet=wallet,
        amount=amount,
        destination=destination,
        status=status,
    )
    if status == PayoutStatus.PENDING:
        wallet.available_balance -= amount
        wallet.held_balance += amount
        wallet.save(update_fields=["available_balance", "held_balance"])
        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type="PAYOUT_RESERVATION",
            amount=amount,
            available_delta=-amount,
            held_delta=amount,
            reference=f"PAYOUT-HOLD-{payout.pk}",
            actor=user,
        )
    return payout


def test_financial_manager_can_filter_and_search_payout_invoices(
    api, farmer, wholesaler, financial_manager
):
    farmer_payout = payout_for(
        farmer, amount="125.00", destination="Telebirr 0912345678"
    )
    payout_for(
        wholesaler,
        amount="250.00",
        destination="Manual bank transfer",
        status=PayoutStatus.PAID,
    )
    api.force_authenticate(user=financial_manager)

    response = api.get(
        "/api/v1/wallet/payouts/",
        {
            "status": "PENDING",
            "role": Role.FARMER,
            "search": str(farmer.id),
            "min_amount": "100",
            "max_amount": "200",
            "method": "MANUAL",
            "ordering": "amount_desc",
        },
    )

    assert response.status_code == 200, response.data
    assert response.data["count"] == 1
    result = response.data["results"][0]
    assert result["id"] == str(farmer_payout.id)
    assert result["wallet_owner_role"] == Role.FARMER
    assert result["wallet_owner_id"] == str(farmer.id)
    assert result["destination"] == "Manual destination ending ****5678"


@pytest.mark.parametrize(
    "query,field",
    [
        ({"min_amount": "NaN"}, "min_amount"),
        ({"max_amount": "-1"}, "max_amount"),
        ({"min_amount": "20", "max_amount": "10"}, "max_amount"),
        ({"method": "CHAPA"}, "method"),
        ({"ordering": "invalid"}, "ordering"),
    ],
)
def test_payout_invoice_filters_validate_inputs(
    api, financial_manager, query, field
):
    api.force_authenticate(user=financial_manager)

    response = api.get("/api/v1/wallet/payouts/", query)

    assert response.status_code == 400
    assert field in response.data.get("error", response.data)


def test_payout_invoice_detail_includes_wallet_ledger_and_history(
    api, farmer, financial_manager
):
    payout = payout_for(farmer, amount="75.00", destination="Manual destination")
    AuditLog.objects.create(
        actor=farmer,
        action="wallet_payout_requested",
        target=str(payout.pk),
        detail="Status: none -> PENDING; amount: 75.00 ETB.",
    )
    api.force_authenticate(user=financial_manager)

    response = api.get(f"/api/v1/wallet/payouts/{payout.pk}/")

    assert response.status_code == 200, response.data
    assert response.data["requester"]["id"] == str(farmer.id)
    assert response.data["requester"]["role"] == Role.FARMER
    assert response.data["wallet"]["requested_amount_reserved"] is True
    assert response.data["eligible_for_manual_confirmation"] is True
    assert response.data["payout"]["destination"] == "Manual destination (masked)"
    assert len(response.data["transactions"]) == 1
    assert response.data["history"][0]["action"] == "wallet_payout_requested"


def test_only_financial_manager_can_read_payout_invoice_detail(
    api, farmer, wholesaler
):
    payout = payout_for(farmer, amount="25.00", destination="Private destination")
    api.force_authenticate(user=wholesaler)

    response = api.get(f"/api/v1/wallet/payouts/{payout.pk}/")

    assert response.status_code == 403


def test_unreserved_payout_cannot_be_paid_or_rejected(
    api, farmer, financial_manager
):
    wallet, _ = Wallet.objects.get_or_create(
        user=farmer,
        defaults={"available_balance": Decimal("100.00")},
    )
    payout = WalletPayoutRequest.objects.create(
        wallet=wallet,
        amount=Decimal("40.00"),
        destination="Manual destination",
    )
    available_before = wallet.available_balance
    held_before = wallet.held_balance
    api.force_authenticate(user=financial_manager)

    response = api.post(
        f"/api/v1/wallet/payouts/{payout.pk}/review/",
        {
            "approve": True,
            "external_reference": "BANK-UNRESERVED-40",
            "notes": "Test review evidence.",
        },
        format="json",
    )

    assert response.status_code == 400
    payout.refresh_from_db()
    wallet.refresh_from_db()
    assert payout.status == PayoutStatus.PENDING
    assert wallet.available_balance == available_before
    assert wallet.held_balance == held_before
    assert not WalletTransaction.objects.filter(
        reference__in=(
            f"PAYOUT-HOLD-{payout.pk}",
            f"PAYOUT-{payout.pk}",
            f"PAYOUT-RETURN-{payout.pk}",
        )
    ).exists()


def test_payout_review_requires_evidence_or_rejection_reason_and_is_audited(
    api, farmer, financial_manager
):
    payout = payout_for(farmer, amount="40.00", destination="Manual destination")
    api.force_authenticate(user=financial_manager)

    missing_reference = api.post(
        f"/api/v1/wallet/payouts/{payout.pk}/review/",
        {"approve": True},
        format="json",
    )
    missing_reason = api.post(
        f"/api/v1/wallet/payouts/{payout.pk}/review/",
        {"approve": False},
        format="json",
    )
    assert missing_reference.status_code == 400
    assert missing_reason.status_code == 400
    assert WalletPayoutRequest.objects.get(pk=payout.pk).status == PayoutStatus.PENDING

    paid = api.post(
        f"/api/v1/wallet/payouts/{payout.pk}/review/",
        {
            "approve": True,
            "external_reference": "BANK-CONFIRM-040",
            "notes": "Matched to the bank transfer statement.",
        },
        format="json",
    )
    assert paid.status_code == 200, paid.data
    assert paid.data["payout_request"]["status"] == PayoutStatus.PAID
    assert AuditLog.objects.filter(
        actor=financial_manager,
        target=str(payout.pk),
        detail__contains="PENDING -> PAID",
    ).exists()

    duplicate = api.post(
        f"/api/v1/wallet/payouts/{payout.pk}/review/",
        {
            "approve": True,
            "external_reference": "BANK-CONFIRM-040",
        },
        format="json",
    )
    assert duplicate.status_code == 400
    assert WalletTransaction.objects.filter(
        reference=f"PAYOUT-{payout.pk}"
    ).count() == 1
    assert Notification.objects.filter(
        recipient=farmer,
        message__contains="confirmed as paid after manual transfer verification",
    ).exists()


def test_rejection_returns_funds_and_notifies_requester_with_reason(
    api, farmer, financial_manager
):
    payout = payout_for(farmer, amount="35.00", destination="Manual destination")
    wallet = payout.wallet
    available_before = wallet.available_balance
    api.force_authenticate(user=financial_manager)

    response = api.post(
        f"/api/v1/wallet/payouts/{payout.pk}/review/",
        {
            "approve": False,
            "notes": "Destination could not be matched to the requester.",
        },
        format="json",
    )

    assert response.status_code == 200, response.data
    payout.refresh_from_db()
    wallet.refresh_from_db()
    assert payout.status == PayoutStatus.REJECTED
    assert payout.review_notes == "Destination could not be matched to the requester."
    assert wallet.available_balance == available_before + payout.amount
    assert wallet.held_balance == 0
    assert Notification.objects.filter(
        recipient=farmer,
        message__contains="Destination could not be matched to the requester.",
    ).exists()


def test_requester_sees_rejection_reason_but_not_internal_settlement_notes(
    api, farmer
):
    paid = payout_for(
        farmer,
        amount="30.00",
        destination="Telebirr 0912345678",
        status=PayoutStatus.PAID,
    )
    paid.review_notes = "Matched internal bank statement investigation."
    paid.external_reference = "BANK-PAID-30"
    paid.save(update_fields=["review_notes", "external_reference"])
    rejected = payout_for(
        farmer,
        amount="15.00",
        destination="Telebirr 0912345678",
        status=PayoutStatus.REJECTED,
    )
    rejected.review_notes = "Account destination did not match the requester."
    rejected.save(update_fields=["review_notes"])
    api.force_authenticate(user=farmer)

    response = api.get("/api/v1/wallet/payouts/")

    assert response.status_code == 200
    by_id = {item["id"]: item for item in response.data["results"]}
    assert by_id[str(paid.pk)]["review_notes"] == ""
    assert by_id[str(rejected.pk)]["review_notes"] == (
        "Account destination did not match the requester."
    )
    assert by_id[str(paid.pk)]["destination"] == "Telebirr 0912345678"
