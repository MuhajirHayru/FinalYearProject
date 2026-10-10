from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from payments.models import (
    FundingStatus,
    PayoutStatus,
    Wallet,
    WalletFundingRequest,
    WalletPayoutRequest,
    WalletTransaction,
    WalletTransactionType,
)
from users.models import Role

pytestmark = pytest.mark.django_db


def _ledger_entry(wallet, transaction_type, amount, reference, created_at):
    entry = WalletTransaction.objects.create(
        wallet=wallet,
        transaction_type=transaction_type,
        amount=Decimal(amount),
        reference=reference,
        external_reference=f"EXT-{reference}",
        description="Report test entry",
    )
    WalletTransaction.objects.filter(pk=entry.pk).update(created_at=created_at)
    return entry


def test_wallet_activity_report_aggregates_completed_ledger_and_zero_days(
    api, financial_manager, farmer, wholesaler
):
    farmer_wallet = Wallet.objects.create(user=farmer)
    today = timezone.localdate()
    activity_day = today - timedelta(days=2)
    timestamp = timezone.make_aware(
        datetime.combine(activity_day, time(hour=12)),
        timezone.get_current_timezone(),
    )
    _ledger_entry(
        farmer_wallet, WalletTransactionType.FUNDING, "125.50", "FUND-1", timestamp
    )
    _ledger_entry(
        farmer_wallet, WalletTransactionType.PAYOUT, "25.00", "PAY-1", timestamp
    )
    # Wallets outside participant roles must not be included in reports.
    admin_wallet = Wallet.objects.create(user=financial_manager)
    _ledger_entry(
        admin_wallet, WalletTransactionType.FUNDING, "900.00", "FUND-ADMIN", timestamp
    )

    api.force_authenticate(user=financial_manager)
    response = api.get(
        "/api/v1/dashboard/wallet-activity/",
        {"date_from": (today - timedelta(days=3)).isoformat(), "date_to": today.isoformat()},
    )

    assert response.status_code == 200
    assert response.data["summary"] == {
        "deposits": {"amount": Decimal("125.50"), "count": 1},
        "payouts": {"amount": Decimal("25.00"), "count": 1},
    }
    assert len(response.data["daily"]) == 4
    day_row = next(row for row in response.data["daily"] if row["date"] == activity_day.isoformat())
    assert day_row["deposits"] == "125.50"
    assert day_row["payouts"] == "25.00"
    zero_day = next(row for row in response.data["daily"] if row["date"] == today.isoformat())
    assert zero_day["deposits"] == "0.00"
    assert zero_day["deposit_count"] == 0


def test_wallet_activity_report_and_export_are_finance_manager_only(api, farmer):
    api.force_authenticate(user=farmer)
    assert api.get("/api/v1/dashboard/wallet-activity/").status_code == 403
    assert api.get("/api/v1/dashboard/wallet-activity/export/").status_code == 403


def test_wallet_activity_report_rejects_invalid_or_oversized_periods(
    api, financial_manager
):
    api.force_authenticate(user=financial_manager)
    assert api.get(
        "/api/v1/dashboard/wallet-activity/", {"date_from": "not-a-date"}
    ).status_code == 400
    assert api.get(
        "/api/v1/dashboard/wallet-activity/",
        {"date_from": "2024-01-01", "date_to": "2025-01-02"},
    ).status_code == 400


def test_wallet_activity_csv_streams_only_completed_participant_ledger_rows(
    api, financial_manager, wholesaler
):
    wallet = Wallet.objects.get(user=wholesaler)
    today = timezone.localdate()
    timestamp = timezone.make_aware(
        datetime.combine(today, time(hour=12)),
        timezone.get_current_timezone(),
    )
    _ledger_entry(wallet, WalletTransactionType.FUNDING, "50.00", "FUND-CSV", timestamp)
    _ledger_entry(
        wallet,
        WalletTransactionType.PAYOUT_RESERVATION,
        "15.00",
        "HOLD-CSV",
        timestamp,
    )
    api.force_authenticate(user=financial_manager)

    response = api.get(
        "/api/v1/dashboard/wallet-activity/export/",
        {"date_from": today.isoformat(), "date_to": today.isoformat()},
    )
    content = b"".join(response.streaming_content).decode("utf-8")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    assert "FUND-CSV" in content
    assert "HOLD-CSV" not in content
    assert "Meles Wholesaler" in content


def test_financial_manager_can_filter_funding_and_payout_requests(
    api, financial_manager, farmer, wholesaler
):
    farmer_wallet = Wallet.objects.create(user=farmer)
    wholesaler_wallet = Wallet.objects.get(user=wholesaler)
    WalletFundingRequest.objects.create(
        wallet=farmer_wallet,
        amount=Decimal("100.00"),
        payment_method="CBE Birr",
        external_reference="FARMER-REF",
        status=FundingStatus.PENDING,
    )
    WalletFundingRequest.objects.create(
        wallet=wholesaler_wallet,
        amount=Decimal("200.00"),
        payment_method="Bank Transfer",
        external_reference="WHOLESALE-REF",
        status=FundingStatus.APPROVED,
    )
    WalletPayoutRequest.objects.create(
        wallet=farmer_wallet,
        amount=Decimal("25.00"),
        destination="details withheld",
        status=PayoutStatus.PENDING,
    )
    WalletPayoutRequest.objects.create(
        wallet=wholesaler_wallet,
        amount=Decimal("30.00"),
        destination="details withheld",
        status=PayoutStatus.PAID,
    )
    api.force_authenticate(user=financial_manager)

    funding = api.get(
        "/api/v1/wallet/funding/",
        {"status": "PENDING", "role": Role.FARMER, "search": "FARMER-REF"},
    )
    payouts = api.get(
        "/api/v1/wallet/payouts/",
        {"status": "PENDING", "role": Role.FARMER},
    )

    assert funding.status_code == 200
    assert funding.data["count"] == 1
    assert funding.data["results"][0]["external_reference"] == "FARMER-REF"
    assert payouts.status_code == 200
    assert payouts.data["count"] == 1
    assert payouts.data["results"][0]["status"] == PayoutStatus.PENDING
