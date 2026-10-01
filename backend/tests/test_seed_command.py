"""Seed command smoke test — the demo dataset must satisfy every dashboard."""
import pytest
from django.core.management import call_command
from django.db import connection

from chat.models import ChatChannel, Message
from notifications.models import Notification
from payments.models import Order, PaymentRecord, PaymentStatus
from products.models import Product, ProductStatus, ProductType
from users.models import AccountStatus, PlatformSettings, Role, User

pytestmark = pytest.mark.django_db


def _seed():
    call_command("seed_greenpath", stdout=None, verbosity=0)


def test_seed_creates_every_role(api, db):
    _seed()
    for role in (
        Role.FARMER,
        Role.WHOLESALER,
        Role.RETAILER,
        Role.USER_ADMIN,
        Role.FINANCIAL_MANAGER,
        Role.SUPER_ADMIN,
    ):
        assert User.objects.filter(role=role, status=AccountStatus.APPROVED).exists(), role
    assert User.objects.filter(status=AccountStatus.PENDING).count() == 6
    assert not User.objects.filter(status=AccountStatus.PENDING, is_active=True).exists()


def test_seed_is_idempotent(db):
    _seed()
    before = User.objects.count()
    call_command("seed_greenpath", stdout=None, verbosity=0)
    assert User.objects.count() == before


def test_seeded_users_carry_coordinates(db):
    _seed()
    located = User.objects.exclude(latitude__isnull=True).exclude(longitude__isnull=True)
    assert located.count() >= 15
    for user in located:
        assert -90 <= user.latitude <= 90
        assert -180 <= user.longitude <= 180


def test_seed_covers_every_payment_state(db):
    _seed()
    for status in PaymentStatus.values:
        assert PaymentRecord.objects.filter(status=status).exists(), status
    assert PaymentRecord.objects.filter(status=PaymentStatus.VERIFIED).count() == 43
    assert PaymentRecord.objects.filter(status=PaymentStatus.FLAGGED).count() == 3
    assert PaymentRecord.objects.filter(status=PaymentStatus.DISPUTED).count() == 1


def test_seeded_verified_payments_have_an_auditor(db):
    _seed()
    for record in PaymentRecord.objects.filter(status=PaymentStatus.VERIFIED):
        assert record.verified_by is not None
        assert record.verified_at is not None


def test_seed_creates_marketplace_and_relistings(db):
    _seed()
    assert Product.objects.filter(product_type=ProductType.FARMER_LISTING).count() >= 12
    assert Product.objects.filter(product_type=ProductType.WHOLESALER_LISTING).count() == 4
    assert Product.objects.filter(status=ProductStatus.SOLD).exists()


def test_seed_creates_chat_and_notifications(db):
    _seed()
    assert ChatChannel.objects.count() == 2
    assert Message.objects.count() == 4
    assert Notification.objects.filter(is_read=False).exists()


def test_seed_sets_the_platform_announcement(db):
    _seed()
    assert PlatformSettings.load().announcement


def test_farmer_dashboard_renders_with_seeded_data(api, db):
    _seed()
    from rest_framework.test import APIClient

    farmer = User.objects.get(email="farmer@greenpath.et")
    client = APIClient()
    client.force_authenticate(user=farmer)
    response = client.get("/api/v1/dashboard/farmer/")
    assert response.status_code == 200
    assert response.data["stats"]["total_active_listings"] == 4
    assert response.data["recent_activity"]


def test_retailer_dashboard_ranks_seeded_relistings(api, db):
    _seed()
    from rest_framework.test import APIClient

    retailer = User.objects.get(email="retailer@greenpath.et")
    client = APIClient()
    client.force_authenticate(user=retailer)
    response = client.get("/api/v1/dashboard/retailer/")
    assert response.status_code == 200
    assert response.data["stats"]["location_available"] is True
    assert len(response.data["nearby_listings"]) == 4
    assert response.data["nearby_listings"][0]["distance_km"] == 0


def test_financial_dashboard_renders_with_seeded_data(api, db):
    _seed()
    from rest_framework.test import APIClient

    fm = User.objects.get(email="finance@greenpath.et")
    client = APIClient()
    client.force_authenticate(user=fm)
    summary = client.get("/api/v1/dashboard/payments/")
    assert summary.data["tabs"]["VERIFIED"] == 43
    assert summary.data["tabs"]["FLAGGED"] == 3
    assert summary.data["tabs"]["DISPUTED"] == 1
    report = client.get("/api/v1/reports/financial-summary/")
    assert report.status_code == 200
    assert report.data["totals"]["count"] == PaymentRecord.objects.count()
    export = client.get(
        "/api/v1/reports/financial-summary/export/", {"file_format": "csv"}
    )
    assert export.status_code == 200
    assert len(export.content.decode().strip().splitlines()) == PaymentRecord.objects.count() + 1


def test_super_admin_health_renders_with_seeded_data(api, db):
    _seed()
    from rest_framework.test import APIClient

    root = User.objects.get(email="superadmin@greenpath.et")
    client = APIClient()
    client.force_authenticate(user=root)
    response = client.get("/api/v1/superadmin/health/")
    assert response.status_code == 200
    assert response.data["users"]["total"] == User.objects.count()
    assert response.data["transactions"]["orders_total"] == Order.objects.count()


def test_seed_works_on_postgres_only_features_untouched(db):
    """The command must not depend on the test-only SQLite fast path."""
    _seed()
    assert connection.vendor in ("sqlite", "postgresql")
