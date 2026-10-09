"""Payout account ownership, encryption, and Financial Manager audit tests."""

from decimal import Decimal

import pytest

from payments.models import BankAccount, PayoutBank, Wallet, WalletPayoutRequest
from users.models import AuditLog

pytestmark = pytest.mark.django_db


def account_payload(bank, *, number="100200300400", **extra):
    return {
        "bank": bank.pk,
        "account_holder_name": "Legal Account Holder",
        "account_number": number,
        "confirm_account_number": number,
        "branch": "Bole",
        "branch_code": "001",
        "account_type": "Savings",
        **extra,
    }


@pytest.mark.parametrize("role_name", ["farmer", "wholesaler", "retailer"])
def test_marketplace_roles_can_register_encrypted_bank_accounts(
    api, role_name, farmer, wholesaler, retailer
):
    user = {"farmer": farmer, "wholesaler": wholesaler, "retailer": retailer}[role_name]
    bank = PayoutBank.objects.get(code="commercial-bank-of-ethiopia")
    api.force_authenticate(user=user)

    response = api.post(
        "/api/v1/wallet/bank-accounts/",
        account_payload(bank, nickname="Income", is_default=True),
        format="json",
    )

    assert response.status_code == 201, response.data
    account = BankAccount.objects.get(pk=response.data["id"])
    assert account.user_id == user.pk
    assert account.account_holder_name == "Legal Account Holder"
    assert account.masked_account_number == "****0400"
    assert response.data["masked_account_number"] == "****0400"
    assert "account_number" not in response.data
    assert "confirm_account_number" not in response.data
    assert "100200300400" not in account.account_number_encrypted
    assert response.data["status"] == "NOT_VERIFIED"


def test_bank_account_confirmation_ownership_and_filter_validation(
    api, farmer, wholesaler
):
    bank = PayoutBank.objects.get(code="commercial-bank-of-ethiopia")
    api.force_authenticate(user=farmer)
    mismatch = api.post(
        "/api/v1/wallet/bank-accounts/",
        {**account_payload(bank), "confirm_account_number": "999999999999"},
        format="json",
    )
    assert mismatch.status_code == 400

    invalid_number = api.post(
        "/api/v1/wallet/bank-accounts/",
        account_payload(bank, number="abc-123"),
        format="json",
    )
    assert invalid_number.status_code == 400
    created = api.post(
        "/api/v1/wallet/bank-accounts/",
        account_payload(bank),
        format="json",
    )
    account_id = created.data["id"]

    api.force_authenticate(user=wholesaler)
    assert api.get(f"/api/v1/wallet/bank-accounts/{account_id}/").status_code == 404
    assert api.patch(
        f"/api/v1/wallet/bank-accounts/{account_id}/",
        {"nickname": "Not mine"},
        format="json",
    ).status_code == 404


def test_finance_list_is_masked_and_sensitive_read_is_audited(
    api, farmer, wholesaler, financial_manager
):
    bank = PayoutBank.objects.get(code="commercial-bank-of-ethiopia")
    api.force_authenticate(user=farmer)
    created = api.post(
        "/api/v1/wallet/bank-accounts/",
        account_payload(bank),
        format="json",
    )
    account_id = created.data["id"]

    api.force_authenticate(user=financial_manager)
    listing = api.get(
        "/api/v1/wallet/bank-accounts/",
        {"role": "FARMER", "bank": bank.code, "search": farmer.full_name},
    )
    assert listing.status_code == 200
    assert listing.data["count"] == 1
    row = listing.data["results"][0]
    assert row["user_id"] == str(farmer.pk)
    assert row["user_name"] == farmer.full_name
    assert row["user_role"] == "FARMER"
    assert row["masked_account_number"] == "****0400"
    assert "account_number" not in row

    details = api.get(
        f"/api/v1/wallet/bank-accounts/{account_id}/full-details/"
    )
    assert details.status_code == 200
    assert details.data["account_number"] == "100200300400"
    assert AuditLog.objects.filter(
        actor=financial_manager,
        action="payout_account_sensitive_view",
        target=account_id,
    ).exists()

    api.force_authenticate(user=wholesaler)
    assert api.get(
        f"/api/v1/wallet/bank-accounts/{account_id}/full-details/"
    ).status_code == 403


def test_financial_manager_can_only_flag_for_review_not_falsely_verify(
    api, farmer, financial_manager
):
    bank = PayoutBank.objects.get(code="commercial-bank-of-ethiopia")
    api.force_authenticate(user=farmer)
    created = api.post(
        "/api/v1/wallet/bank-accounts/",
        account_payload(bank),
        format="json",
    )
    account_id = created.data["id"]
    api.force_authenticate(user=financial_manager)

    missing_reason = api.post(
        f"/api/v1/wallet/bank-accounts/{account_id}/require-review/",
        {"notes": ""},
        format="json",
    )
    assert missing_reason.status_code == 400
    review = api.post(
        f"/api/v1/wallet/bank-accounts/{account_id}/require-review/",
        {"notes": "Name needs manual confirmation"},
        format="json",
    )
    assert review.status_code == 200, review.data
    assert review.data["status"] == "REQUIRES_REVIEW"
    assert AuditLog.objects.filter(
        actor=financial_manager,
        action="payout_account_review_requested",
        target=account_id,
    ).exists()
    assert not hasattr(BankAccount.objects.get(pk=account_id), "verified_at")


def test_default_account_switching_and_active_payout_protection(
    api, farmer, financial_manager
):
    bank = PayoutBank.objects.get(code="commercial-bank-of-ethiopia")
    api.force_authenticate(user=farmer)
    first = api.post(
        "/api/v1/wallet/bank-accounts/",
        account_payload(bank, number="100200300400", is_default=True),
        format="json",
    )
    second = api.post(
        "/api/v1/wallet/bank-accounts/",
        account_payload(bank, number="400300200100", is_default=True),
        format="json",
    )
    assert first.status_code == second.status_code == 201
    assert BankAccount.objects.filter(user=farmer, is_default=True).count() == 1
    account = BankAccount.objects.get(pk=second.data["id"])

    wallet = Wallet.objects.create(user=farmer, available_balance=Decimal("100.00"))
    WalletPayoutRequest.objects.create(
        wallet=wallet,
        payout_account=account,
        amount=Decimal("25.00"),
        destination=f"{bank.name} {account.masked_account_number}",
    )
    assert api.patch(
        f"/api/v1/wallet/bank-accounts/{account.pk}/",
        {"nickname": "Edited"},
        format="json",
    ).status_code == 400
    assert api.delete(f"/api/v1/wallet/bank-accounts/{account.pk}/").status_code == 400

    api.force_authenticate(user=financial_manager)
    status_edit = api.patch(
        f"/api/v1/wallet/bank-accounts/{account.pk}/",
        {"status": "VERIFIED"},
        format="json",
    )
    assert status_edit.status_code == 400
