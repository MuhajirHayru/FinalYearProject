"""Dashboard, payment summary and report tests (FR-F-06, FR-W-07, FR-R-05, FR-FM-01..04)."""
from decimal import Decimal

import pytest

from chat.models import ChatChannel, Message
from notifications.models import Notification
from payments.models import (
    FundingStatus,
    Order,
    OrderStatus,
    PaymentRecord,
    PaymentStatus,
    PayoutStatus,
    Wallet,
    WalletFundingRequest,
    WalletPayoutRequest,
)
from products.models import Product, ProductStatus, ProductType
from users.models import AccountStatus, Role, User

pytestmark = pytest.mark.django_db


def _payment(submitter, farmer, product, amount, status=PaymentStatus.PENDING, ref="FT-1"):
    return PaymentRecord.objects.create(
        submitted_by=submitter,
        farmer=farmer,
        product=product,
        amount=Decimal(amount),
        status=status,
        reference_number=ref,
    )


# ---------------------------------------------------------------------------
# Farmer dashboard
# ---------------------------------------------------------------------------
def test_farmer_dashboard_aggregates(api, farmer, farmer_product, wholesaler, payment):
    Notification.objects.create(recipient=farmer, type="ORDER", message="New order")
    api.force_authenticate(user=farmer)
    response = api.get("/api/v1/dashboard/farmer/")
    assert response.status_code == 200
    stats = response.data["stats"]
    assert stats["total_active_listings"] == 1
    assert stats["pending_payments"] == 1
    assert stats["total_earned"] == 0
    assert response.data["listings"][0]["title"] == "Tomato"
    assert response.data["recent_activity"][0]["type"] == "ORDER"
    assert response.data["recent_activity"][0]["time"]


def test_farmer_dashboard_earned_total_only_counts_verified(
    api, farmer, farmer_product, wholesaler, payment, financial_manager
):
    payment.verify(financial_manager)
    api.force_authenticate(user=farmer)
    response = api.get("/api/v1/dashboard/farmer/")
    assert response.data["stats"]["total_earned"] == 1250
    assert response.data["stats"]["pending_payments"] == 0


def test_farmer_dashboard_counts_unread_messages(api, farmer, wholesaler):
    channel = ChatChannel.objects.create()
    channel.participants.add(farmer, wholesaler)
    Message.objects.create(channel=channel, sender=wholesaler, content="Are you open?")
    api.force_authenticate(user=farmer)
    assert api.get("/api/v1/dashboard/farmer/").data["stats"]["unread_messages"] == 1


def test_farmer_dashboard_pending_orders(api, farmer, farmer_product, wholesaler, order):
    api.force_authenticate(user=farmer)
    assert api.get("/api/v1/dashboard/farmer/").data["stats"]["pending_orders"] == 1


def test_dashboards_are_role_isolated(api, farmer, wholesaler, retailer, user_admin):
    paths = {
        farmer: "/api/v1/dashboard/farmer/",
        wholesaler: "/api/v1/dashboard/wholesaler/",
        retailer: "/api/v1/dashboard/retailer/",
    }
    for user, path in paths.items():
        for other, other_path in paths.items():
            if user.pk == other.pk:
                continue
            api.force_authenticate(user=other)
            assert api.get(path).status_code == 403, (other.role, path)


# ---------------------------------------------------------------------------
# Wholesaler dashboard
# ---------------------------------------------------------------------------
def test_wholesaler_dashboard(api, wholesaler, order, payment):
    api.force_authenticate(user=wholesaler)
    response = api.get("/api/v1/dashboard/wholesaler/")
    assert response.status_code == 200
    stats = response.data["stats"]
    assert stats["total_orders"] == 1
    assert stats["total_spent"] == 1250
    assert stats["pending_payments"] == 1
    assert stats["verified_payments"] == 0
    assert response.data["orders"][0]["reference"] == order.reference
    assert response.data["orders"][0]["total"].endswith("ETB")


def test_wholesaler_dashboard_excludes_cancelled_spend(api, wholesaler, order):
    order.set_status(OrderStatus.CANCELLED)
    api.force_authenticate(user=wholesaler)
    stats = api.get("/api/v1/dashboard/wholesaler/").data["stats"]
    assert stats["total_orders"] == 1
    assert stats["total_spent"] == 0


def test_wholesaler_dashboard_counts_favorite_sellers(api, wholesaler, farmer, farmer_product):
    for _ in range(2):
        api.force_authenticate(user=wholesaler)
        api.post(
            "/api/v1/orders/",
            {"product": str(farmer_product.id), "quantity": "5"},
            format="json",
        )
    api.force_authenticate(user=wholesaler)
    stats = api.get("/api/v1/dashboard/wholesaler/").data["stats"]
    assert stats["favorite_sellers"] == 1
    assert stats["pending_orders"] == 2


# ---------------------------------------------------------------------------
# Retailer dashboard
# ---------------------------------------------------------------------------
def test_retailer_dashboard_ranks_nearby_listings(api, retailer, wholesaler):
    Product.objects.create(
        title="Mango",
        description="",
        category="Fruits",
        quantity=100,
        unit_of_measure="kg",
        price_per_unit=Decimal("30"),
        owner=wholesaler,
        product_type=ProductType.WHOLESALER_LISTING,
        status=ProductStatus.ACTIVE,
    )
    api.force_authenticate(user=retailer)
    response = api.get("/api/v1/dashboard/retailer/")
    assert response.status_code == 200
    assert response.data["stats"]["location_available"] is True
    listing = response.data["nearby_listings"][0]
    assert listing["title"] == "Mango"
    assert listing["wholesaler"] == wholesaler.full_name
    assert listing["distance_km"] is not None
    assert response.data["stats"]["nearby_listings"] == 1


def test_retailer_dashboard_without_coordinates_has_no_distance(api, wholesaler):
    Product.objects.create(
        title="Mango",
        description="",
        category="Fruits",
        quantity=100,
        unit_of_measure="kg",
        price_per_unit=Decimal("30"),
        owner=wholesaler,
        product_type=ProductType.WHOLESALER_LISTING,
        status=ProductStatus.ACTIVE,
    )
    locateless = User.objects.create_user(
        email="nomap@test.et",
        password="demo1234",
        full_name="No Map Retailer",
        role=Role.RETAILER,
        status=AccountStatus.APPROVED,
        privacy_policy_accepted=True,
        location="Sidama",
    )
    api.force_authenticate(user=locateless)
    response = api.get("/api/v1/dashboard/retailer/")
    assert response.data["stats"]["location_available"] is False
    assert response.data["nearby_listings"][0]["distance_km"] is None


def test_retailer_dashboard_hides_inactive_listings(api, retailer, wholesaler):
    Product.objects.create(
        title="Stale",
        description="",
        category="Fruits",
        quantity=5,
        unit_of_measure="kg",
        price_per_unit=Decimal("10"),
        owner=wholesaler,
        product_type=ProductType.WHOLESALER_LISTING,
        status=ProductStatus.INACTIVE,
    )
    api.force_authenticate(user=retailer)
    assert api.get("/api/v1/dashboard/retailer/").data["nearby_listings"] == []


# ---------------------------------------------------------------------------
# Admin / financial dashboards
# ---------------------------------------------------------------------------
def test_admin_dashboard_counts_users_by_role(api, user_admin, pending_user, farmer):
    api.force_authenticate(user=user_admin)
    response = api.get("/api/v1/dashboard/admin/")
    assert response.status_code == 200
    stats = response.data["stats"]
    assert stats["pending_users"] == 1
    assert stats["total_users"] == User.objects.count()
    assert stats["farmers"] >= 1
    assert stats["total_orders"] == Order.objects.count()


def test_financial_manager_can_read_the_admin_dashboard(api, financial_manager, payment):
    api.force_authenticate(user=financial_manager)
    stats = api.get("/api/v1/dashboard/admin/").data["stats"]
    assert stats["pending_payments"] == 1
    assert stats["verified_payments"] == 0


def test_financial_operations_summary_aggregates_wallet_queues(
    api, financial_manager, farmer, wholesaler
):
    farmer_wallet, _ = Wallet.objects.get_or_create(user=farmer)
    farmer_wallet.available_balance = Decimal("125.50")
    farmer_wallet.held_balance = Decimal("5.00")
    farmer_wallet.save()
    wholesaler_wallet, _ = Wallet.objects.get_or_create(user=wholesaler)
    wholesaler_wallet.available_balance = Decimal("25.25")
    wholesaler_wallet.held_balance = Decimal("2.50")
    wholesaler_wallet.save()
    WalletFundingRequest.objects.create(
        wallet=farmer_wallet,
        amount=Decimal("50.25"),
        payment_method="Chapa",
        external_reference="SUMMARY-FUND-1",
        status=FundingStatus.AWAITING_APPROVAL,
    )
    WalletFundingRequest.objects.create(
        wallet=farmer_wallet,
        amount=Decimal("10.00"),
        payment_method="Bank Transfer",
        external_reference="SUMMARY-FUND-2",
        status=FundingStatus.FAILED,
    )
    WalletPayoutRequest.objects.create(
        wallet=farmer_wallet,
        amount=Decimal("20.75"),
        destination="registered account",
        status=PayoutStatus.PENDING,
    )

    api.force_authenticate(user=financial_manager)
    response = api.get("/api/v1/dashboard/financial-operations/")

    assert response.status_code == 200
    assert response.data["wallets"] == {
        "count": 2,
        "available_balance": "150.75",
        "held_balance": "7.50",
        "by_role": {
            "FARMER": {
                "count": 1,
                "available_balance": "125.50",
                "held_balance": "5.00",
            },
            "WHOLESALER": {
                "count": 1,
                "available_balance": "25.25",
                "held_balance": "2.50",
            },
        },
    }
    assert response.data["funding"]["awaiting_review_count"] == 1
    assert response.data["funding"]["awaiting_review_amount"] == "50.25"
    assert response.data["funding"]["by_status"]["FAILED"]["count"] == 1
    assert response.data["payouts"]["pending_count"] == 1
    assert response.data["payouts"]["pending_amount"] == "20.75"
    assert response.data["beneficiaries"] == {
        "count": 0,
        "requires_review_count": 0,
    }


def test_financial_operations_summary_is_financial_manager_only(api, user_admin):
    api.force_authenticate(user=user_admin)
    assert api.get("/api/v1/dashboard/financial-operations/").status_code == 403


def test_dashboard_admin_is_closed_to_regular_users(api, farmer):
    api.force_authenticate(user=farmer)
    assert api.get("/api/v1/dashboard/admin/").status_code == 403


def test_payment_summary_view(api, financial_manager, wholesaler, farmer, farmer_product):
    _payment(wholesaler, farmer, farmer_product, "100")
    verified = _payment(wholesaler, farmer, farmer_product, "200")
    verified.verify(financial_manager)
    flagged = _payment(wholesaler, farmer, farmer_product, "300", ref="FT-FLAG")
    flagged.verify(financial_manager)  # sets verified_at
    flagged.status = PaymentStatus.FLAGGED
    flagged.save()

    api.force_authenticate(user=financial_manager)
    response = api.get("/api/v1/dashboard/payments/")
    summary = response.data["summary"]
    assert summary["pending_amount"] == 100
    assert summary["pending_count"] == 1
    assert summary["verified_amount"] == 200
    assert summary["verified_count"] == 1
    assert summary["flagged_count"] == 1
    assert response.data["tabs"] == {
        "PENDING": 1,
        "VERIFIED": 1,
        "FLAGGED": 1,
        "DISPUTED": 0,
    }


def test_payment_summary_is_financial_manager_only(api, wholesaler):
    api.force_authenticate(user=wholesaler)
    assert api.get("/api/v1/dashboard/payments/").status_code == 403


# ---------------------------------------------------------------------------
# Financial reports
# ---------------------------------------------------------------------------
def test_financial_report_totals(api, financial_manager, wholesaler, farmer, farmer_product):
    _payment(wholesaler, farmer, farmer_product, "100")
    _payment(wholesaler, farmer, farmer_product, "250", status=PaymentStatus.VERIFIED)
    api.force_authenticate(user=financial_manager)
    response = api.get("/api/v1/reports/financial-summary/")
    assert response.status_code == 200
    totals = response.data["totals"]
    assert totals["count"] == 2
    assert totals["amount"] == 350
    assert totals["by_status"]["PENDING"]["count"] == 1
    assert totals["by_status"]["VERIFIED"]["total"] == 250
    assert totals["by_method"]["CBE Birr"]["count"] == 2
    assert totals["top_farmers"][0]["farmer"] == farmer.full_name
    assert totals["top_wholesalers"][0]["wholesaler"] == wholesaler.full_name


def test_financial_report_filters(api, financial_manager, wholesaler, farmer, farmer_product):
    _payment(wholesaler, farmer, farmer_product, "100", ref="AAA-1")
    _payment(
        wholesaler, farmer, farmer_product, "200", ref="BBB-2", status=PaymentStatus.VERIFIED
    )
    api.force_authenticate(user=financial_manager)
    assert api.get("/api/v1/reports/financial-summary/", {"status": "PENDING"}).data["totals"]["amount"] == 100
    assert api.get("/api/v1/reports/financial-summary/", {"search": "BBB"}).data["totals"]["amount"] == 200
    assert api.get("/api/v1/reports/financial-summary/", {"user_id": str(farmer.id)}).data["totals"]["amount"] == 300
    assert api.get("/api/v1/reports/financial-summary/", {"user_id": str(farmer.id), "status": "VERIFIED"}).data["totals"]["amount"] == 200
    assert api.get("/api/v1/reports/financial-summary/", {"user_id": str(farmer.id), "status": "FLAGGED"}).data["totals"]["count"] == 0


def test_financial_report_is_financial_manager_only(api, user_admin):
    api.force_authenticate(user=user_admin)
    assert api.get("/api/v1/reports/financial-summary/").status_code == 403
    assert api.get("/api/v1/reports/financial-summary/export/").status_code == 403
    assert api.get("/api/v1/reports/transaction-volume/").status_code == 403


def test_csv_export_matches_the_summary(api, financial_manager, wholesaler, farmer, farmer_product):
    record = _payment(wholesaler, farmer, farmer_product, "777.25", ref="FT-EXPORT")
    api.force_authenticate(user=financial_manager)
    response = api.get("/api/v1/reports/financial-summary/export/", {"file_format": "csv"})
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    assert "attachment" in response["Content-Disposition"]
    assert response["Content-Disposition"].endswith('.csv"')
    body = response.content.decode()
    lines = body.strip().splitlines()
    assert lines[0].startswith("Payment ID,Wholesaler,Farmer,Product")
    assert len(lines) == 2
    assert record.display_id in lines[1]
    assert "777.25" in lines[1]
    assert "FT-EXPORT" in lines[1]


def test_pdf_export_is_a_valid_pdf(api, financial_manager, wholesaler, farmer, farmer_product):
    _payment(wholesaler, farmer, farmer_product, "100")
    api.force_authenticate(user=financial_manager)
    response = api.get("/api/v1/reports/financial-summary/export/", {"file_format": "pdf"})
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    body = bytes(response.content)
    assert body.startswith(b"%PDF-1.4")
    assert body.rstrip().endswith(b"%%EOF")
    assert b"/Type /Catalog" in body


def test_export_defaults_to_csv(api, financial_manager, wholesaler, farmer, farmer_product):
    _payment(wholesaler, farmer, farmer_product, "100")
    api.force_authenticate(user=financial_manager)
    response = api.get("/api/v1/reports/financial-summary/export/")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"


def test_export_rejects_an_unknown_format(api, financial_manager):
    api.force_authenticate(user=financial_manager)
    response = api.get("/api/v1/reports/financial-summary/export/", {"file_format": "xlsx"})
    assert response.status_code == 400


def test_export_honours_filters(api, financial_manager, wholesaler, farmer, farmer_product):
    _payment(wholesaler, farmer, farmer_product, "100", ref="KEEP")
    _payment(wholesaler, farmer, farmer_product, "900", ref="DROP", status=PaymentStatus.VERIFIED)
    api.force_authenticate(user=financial_manager)
    body = api.get(
        "/api/v1/reports/financial-summary/export/",
        {"file_format": "csv", "status": "PENDING"},
    ).content.decode()
    assert "KEEP" in body
    assert "DROP" not in body


def test_transaction_volume_series(api, financial_manager, wholesaler, farmer, farmer_product):
    _payment(wholesaler, farmer, farmer_product, "100")
    _payment(wholesaler, farmer, farmer_product, "200", ref="FT-2")
    api.force_authenticate(user=financial_manager)
    response = api.get("/api/v1/reports/transaction-volume/", {"days": 30})
    assert response.status_code == 200
    assert response.data["days"] == 30
    assert response.data["series"][-1]["count"] == 2
    assert response.data["series"][-1]["total"] == 300


def test_transaction_volume_clamps_the_window(api, financial_manager):
    api.force_authenticate(user=financial_manager)
    assert api.get("/api/v1/reports/transaction-volume/", {"days": "5000"}).data["days"] == 365


def test_transaction_volume_excludes_records_outside_the_window(
    api, financial_manager, wholesaler, farmer, farmer_product
):
    from datetime import timedelta

    from django.utils import timezone

    old = _payment(wholesaler, farmer, farmer_product, "100")
    PaymentRecord.objects.filter(pk=old.pk).update(
        submitted_at=timezone.now() - timedelta(days=90)
    )
    api.force_authenticate(user=financial_manager)
    assert api.get("/api/v1/reports/transaction-volume/", {"days": 7}).data["series"] == []
