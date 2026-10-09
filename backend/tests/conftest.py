"""Shared pytest fixtures for the Green Path backend suite (NFR-10)."""
import pytest
from rest_framework.test import APIClient

from chat.models import ChatChannel
from payments.models import Order, PaymentRecord, Wallet
from products.models import Product, ProductType
from users.models import AccountStatus, Role, User


def make_user(role, email, name="Test User", password="demo1234", **extra):
    extra.setdefault("status", AccountStatus.APPROVED)
    extra.setdefault("privacy_policy_accepted", True)
    return User.objects.create_user(
        email=email, password=password, full_name=name, role=role, **extra
    )


@pytest.fixture
def farmer(db):
    return make_user(Role.FARMER, "farmer@test.et", "Abebe Farmer", location="Amhara")


@pytest.fixture
def farmer_b(db):
    return make_user(Role.FARMER, "farmer2@test.et", "Bekele Farmer", location="Oromia")


@pytest.fixture
def wholesaler(db):
    user = make_user(
        Role.WHOLESALER, "wholesaler@test.et", "Meles Wholesaler",
        location="Addis Ababa", latitude=9.0300, longitude=38.7400,
    )
    Wallet.objects.create(user=user, available_balance="100000.00")
    return user


@pytest.fixture
def wholesaler_b(db):
    user = make_user(
        Role.WHOLESALER, "wholesaler2@test.et", "Selam Wholesaler",
        location="Addis Ababa", latitude=9.0200, longitude=38.7500,
    )
    Wallet.objects.create(user=user, available_balance="100000.00")
    return user


@pytest.fixture
def retailer(db):
    user = make_user(
        Role.RETAILER, "retailer@test.et", "Mulu Retail",
        location="Addis Ababa", latitude=9.0300, longitude=38.7400,
    )
    Wallet.objects.create(user=user, available_balance="100000.00")
    return user


@pytest.fixture
def user_admin(db):
    return make_user(Role.USER_ADMIN, "useradmin@test.et", "Hana Admin")


@pytest.fixture
def financial_manager(db):
    return make_user(Role.FINANCIAL_MANAGER, "finance@test.et", "Yohannes Finance")


@pytest.fixture
def super_admin(db):
    return make_user(
        Role.SUPER_ADMIN, "superadmin@test.et", "Super Admin",
        is_staff=True, is_superuser=True,
    )


@pytest.fixture
def pending_user(db):
    return User.objects.create_user(
        email="pending@test.et", password="demo1234", full_name="Pending Person",
        role=Role.FARMER, status=AccountStatus.PENDING, location="SNNPR",
    )


@pytest.fixture
def farmer_product(db, farmer):
    return Product.objects.create(
        title="Tomato", category="Vegetables", quantity=200, unit_of_measure="kg",
        price_per_unit=25, owner=farmer, product_type=ProductType.FARMER_LISTING,
        description="Fresh tomato.",
    )


@pytest.fixture
def wholesaler_product(db, wholesaler):
    return Product.objects.create(
        title="Wholesale Tomato", category="Vegetables", quantity=500,
        unit_of_measure="kg", price_per_unit=30, owner=wholesaler,
        product_type=ProductType.WHOLESALER_LISTING, description="Bulk tomato.",
    )


@pytest.fixture
def chat_channel(db, farmer, wholesaler, farmer_product):
    channel = ChatChannel.objects.create(related_product=farmer_product)
    channel.participants.add(farmer, wholesaler)
    return channel


@pytest.fixture
def order(db, wholesaler, farmer_product):
    return Order.objects.create(
        reference="#ORD900001", wholesaler=wholesaler, farmer=farmer_product.owner,
        product=farmer_product, quantity=50, total_amount=1250, status="Processing",
    )


@pytest.fixture
def payment(db, wholesaler, farmer, farmer_product):
    return PaymentRecord.objects.create(
        submitted_by=wholesaler, farmer=farmer, product=farmer_product,
        amount=1250, payment_method="CBE Birr", reference_number="CBE-1",
    )


@pytest.fixture
def api(db):
    return APIClient()


@pytest.fixture
def auth(api, farmer):
    api.force_authenticate(user=farmer)
    return api


def login(api, user, password="demo1234"):
    api.force_authenticate(user=user)
    return api
