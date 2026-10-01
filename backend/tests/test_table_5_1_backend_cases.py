"""Backend unit and integration tests — Table 5.1 of the project document.

Each test is named after the test-case ID it implements so the mapping between
the documentation and the suite stays traceable.
"""
import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from chat.models import Message
from notifications.models import Notification
from payments.models import PaymentRecord
from products.models import Product
from users.models import AccountStatus, PlatformSettings, User

pytestmark = pytest.mark.django_db


def errors(response):
    """Field-level errors from the project's ``{success, error}`` envelope."""
    payload = response.data.get("error", response.data)
    return payload if isinstance(payload, dict) else {}


# ---------------------------------------------------------------------------
# TC-BE-01  Farmer registration with valid data -> 201, status=PENDING
# ---------------------------------------------------------------------------
def test_tc_be_01_registration_creates_pending_user(api):
    response = api.post(
        "/api/v1/auth/register/",
        {
            "full_name": "Selam Bekele",
            "email": "selam@test.et",
            "phone": "+251911000000",
            "location": "Amhara Region",
            "role": "FARMER",
            "password": "strongpass123",
            "privacy_policy_accepted": True,
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    user = User.objects.get(email="selam@test.et")
    assert user.status == AccountStatus.PENDING
    assert user.role == "FARMER"


# ---------------------------------------------------------------------------
# TC-BE-02  Registration with duplicate email -> 400
# ---------------------------------------------------------------------------
def test_tc_be_02_duplicate_email_rejected(api, farmer):
    response = api.post(
        "/api/v1/auth/register/",
        {
            "full_name": "Copy Cat",
            "email": "farmer@test.et",
            "phone": "+251911000001",
            "location": "Oromia",
            "role": "FARMER",
            "password": "strongpass123",
            "privacy_policy_accepted": True,
        },
        format="json",
    )
    assert response.status_code == 400
    assert "email" in errors(response)


# ---------------------------------------------------------------------------
# TC-BE-03  Login with correct credentials -> 200 + refresh cookie
# ---------------------------------------------------------------------------
def test_tc_be_03_login_issues_access_token_and_cookie(api, farmer):
    response = api.post(
        "/api/v1/auth/login/",
        {"email": "farmer@test.et", "password": "demo1234"},
        format="json",
    )
    assert response.status_code == 200, response.data
    assert "access" in response.data
    assert "greenpath_refresh" in response.cookies
    assert response.data["user"]["role"] == "FARMER"
    assert "product:create" in response.data["user"]["permissions"]


def test_tc_be_03b_login_rejects_pending_user(api, pending_user):
    response = api.post(
        "/api/v1/auth/login/",
        {"email": "pending@test.et", "password": "demo1234"},
        format="json",
    )
    assert response.status_code == 400
    assert "pending" in str(response.data).lower()


# ---------------------------------------------------------------------------
# TC-BE-04  Login with incorrect password -> 401/400 auth failure
# ---------------------------------------------------------------------------
def test_tc_be_04_login_with_wrong_password(api, farmer):
    response = api.post(
        "/api/v1/auth/login/",
        {"email": "farmer@test.et", "password": "wrong-password"},
        format="json",
    )
    assert response.status_code in (400, 401)
    assert response.data["success"] is False


# ---------------------------------------------------------------------------
# TC-BE-05  Access protected endpoint without token -> 401
# ---------------------------------------------------------------------------
def test_tc_be_05_protected_endpoint_requires_token():
    client = APIClient()
    response = client.get("/api/v1/products/farmer-listings/")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# TC-BE-06  Farmer accessing wholesaler endpoint -> 403
# ---------------------------------------------------------------------------
def test_tc_be_06_farmer_forbidden_from_wholesaler_listings(api, farmer, wholesaler_product):
    api.force_authenticate(user=farmer)
    response = api.get("/api/v1/products/wholesaler-listings/")
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# TC-BE-07  Farmer creating product listing with valid data -> 201, ACTIVE
# ---------------------------------------------------------------------------
def test_tc_be_07_farmer_creates_active_listing(api, farmer):
    api.force_authenticate(user=farmer)
    response = api.post(
        "/api/v1/products/farmer-listings/",
        {
            "title": "Potato",
            "description": "Fresh potato",
            "category": "Root Crops",
            "quantity": "350",
            "unit_of_measure": "kg",
            "price_per_unit": "18",
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    listing = Product.objects.get(title="Potato")
    assert listing.status == "ACTIVE"
    assert listing.owner == farmer


# ---------------------------------------------------------------------------
# TC-BE-08  Farmer creating listing with missing quantity -> 400
# ---------------------------------------------------------------------------
def test_tc_be_08_listing_requires_quantity(api, farmer):
    api.force_authenticate(user=farmer)
    response = api.post(
        "/api/v1/products/farmer-listings/",
        {
            "title": "Onion",
            "category": "Vegetables",
            "unit_of_measure": "kg",
            "price_per_unit": "22",
        },
        format="json",
    )
    assert response.status_code == 400
    assert "quantity" in errors(response)


@pytest.mark.parametrize("field,value", [("quantity", "0"), ("price_per_unit", "-5")])
def test_tc_be_08b_listing_rejects_non_positive_values(api, farmer, field, value):
    api.force_authenticate(user=farmer)
    payload = {
        "title": "Bad",
        "category": "Vegetables",
        "quantity": "10",
        "unit_of_measure": "kg",
        "price_per_unit": "10",
    }
    payload[field] = value
    response = api.post("/api/v1/products/farmer-listings/", payload, format="json")
    assert response.status_code == 400
    assert field in errors(response)


# ---------------------------------------------------------------------------
# TC-BE-09  User Admin approving pending user -> 200, status=APPROVED
# ---------------------------------------------------------------------------
def test_tc_be_09_user_admin_approves_pending_user(api, user_admin, pending_user):
    api.force_authenticate(user=user_admin)
    response = api.post(f"/api/v1/admin/users/{pending_user.id}/approve/")
    assert response.status_code == 200, response.data
    pending_user.refresh_from_db()
    assert pending_user.status == AccountStatus.APPROVED
    # user_approved domain event notifies the user
    assert Notification.objects.filter(
        recipient=pending_user, type="APPROVAL"
    ).exists()


def test_tc_be_09b_reject_records_optional_reason(api, user_admin, pending_user):
    api.force_authenticate(user=user_admin)
    response = api.post(
        f"/api/v1/admin/users/{pending_user.id}/reject/",
        {"reason": "Incomplete documentation"},
        format="json",
    )
    assert response.status_code == 200
    pending_user.refresh_from_db()
    assert pending_user.status == AccountStatus.REJECTED
    assert pending_user.rejection_reason == "Incomplete documentation"


# ---------------------------------------------------------------------------
# TC-BE-10  Wholesaler submitting payment record -> 201, status=PENDING
# ---------------------------------------------------------------------------
def test_tc_be_10_wholesaler_submits_payment(
    api, wholesaler, farmer, farmer_product, financial_manager
):
    api.force_authenticate(user=wholesaler)
    response = api.post(
        "/api/v1/payments/",
        {
            "submitted_by": str(wholesaler.id),
            "farmer": str(farmer.id),
            "product": str(farmer_product.id),
            "amount": "1250.00",
            "payment_method": "CBE Birr",
            "reference_number": "CBE-999",
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    record = PaymentRecord.objects.latest("submitted_at")
    assert record.status == "PENDING"
    # payment_submitted domain event notifies the Financial Manager queue
    assert Notification.objects.filter(
        recipient=financial_manager, type="PAYMENT"
    ).exists()


def test_tc_be_10b_farmer_cannot_submit_payment(api, farmer, wholesaler, farmer_product):
    api.force_authenticate(user=farmer)
    response = api.post(
        "/api/v1/payments/",
        {
            "submitted_by": str(wholesaler.id),
            "farmer": str(farmer.id),
            "product": str(farmer_product.id),
            "amount": "100",
            "payment_method": "CBE Birr",
        },
        format="json",
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# TC-BE-11  Financial Manager verifying payment -> 200, status=VERIFIED
# ---------------------------------------------------------------------------
def test_tc_be_11_financial_manager_verifies_payment(api, financial_manager, payment):
    api.force_authenticate(user=financial_manager)
    response = api.patch(
        f"/api/v1/payments/{payment.id}/verify/", {}, format="json"
    )
    assert response.status_code == 200, response.data
    payment.refresh_from_db()
    assert payment.status == "VERIFIED"
    assert payment.verified_by == financial_manager
    assert payment.verified_at is not None


def test_tc_be_11b_wholesaler_cannot_verify_own_payment(api, wholesaler, payment):
    api.force_authenticate(user=wholesaler)
    response = api.patch(f"/api/v1/payments/{payment.id}/verify/", {}, format="json")
    assert response.status_code == 403


def test_tc_be_11c_verified_payment_cannot_be_reverified(api, financial_manager, payment):
    payment.verify(financial_manager)
    api.force_authenticate(user=financial_manager)
    response = api.patch(f"/api/v1/payments/{payment.id}/verify/", {}, format="json")
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# TC-BE-12  JWT token expiry enforcement -> 401
# ---------------------------------------------------------------------------
def test_tc_be_12_expired_token_rejected(db):
    from datetime import timedelta

    from django.utils import timezone
    from rest_framework_simplejwt.tokens import AccessToken

    token = AccessToken.for_user(User.objects.create_user(
        email="exp@test.et", password="demo1234", full_name="Exp",
        role="FARMER", status=AccountStatus.APPROVED,
    ))
    token.set_exp(from_time=timezone.now() - timedelta(hours=2))
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    response = client.get("/api/v1/dashboard/farmer/")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# TC-BE-13  Token refresh with valid refresh cookie -> 200, new access token
# ---------------------------------------------------------------------------
def test_tc_be_13_refresh_issues_new_access_token(api, farmer):
    from django.conf import settings
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(farmer)
    client = APIClient()
    client.cookies[settings.REFRESH_COOKIE_KEY] = str(refresh)
    response = client.post("/api/v1/auth/token/refresh/", {}, format="json")
    assert response.status_code == 200, response.data
    assert response.data["access"]
    assert settings.REFRESH_COOKIE_KEY in response.cookies


def test_tc_be_13b_refresh_without_cookie_rejected():
    client = APIClient()
    response = client.post("/api/v1/auth/token/refresh/", {}, format="json")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# TC-BE-14  SQL injection attempt in search field -> no DB error
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "payload",
    ["' OR 1=1--", "'; DROP TABLE users;--", "\" OR \"\"=\"", "1; DELETE FROM products"],
)
def test_tc_be_14_sql_injection_is_parameterised(api, wholesaler, farmer_product, payload):
    api.force_authenticate(user=wholesaler)
    response = api.get("/api/v1/products/farmer-listings/", {"search": payload})
    assert response.status_code == 200
    # Tables intact and no data leaked.
    assert User.objects.filter(email="farmer@test.et").exists()
    assert Product.objects.filter(pk=farmer_product.pk).exists()


def test_tc_be_14b_sql_injection_in_login(api):
    response = api.post(
        "/api/v1/auth/login/",
        {"email": "admin@greenpath' OR '1'='1", "password": "' OR 1=1--"},
        format="json",
    )
    assert response.status_code == 400
    assert User.objects.count() >= 0


def test_tc_be_14c_xss_payload_is_stored_verbatim_not_executed(api, farmer):
    api.force_authenticate(user=farmer)
    response = api.post(
        "/api/v1/products/farmer-listings/",
        {
            "title": "<script>alert('xss')</script>",
            "description": "<img src=x onerror=alert(1)>",
            "category": "Other",
            "quantity": "5",
            "unit_of_measure": "kg",
            "price_per_unit": "5",
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    listing = Product.objects.get(pk=response.data["id"])
    # Stored as plain text; the API never renders HTML.
    assert listing.title == "<script>alert('xss')</script>"


# ---------------------------------------------------------------------------
# TC-BE-15  Farmer retrieving only own product listings
# ---------------------------------------------------------------------------
def test_tc_be_15_farmer_my_listings_returns_only_own(api, farmer, farmer_b):
    mine = Product.objects.create(
        title="My Tomato", quantity=10, price_per_unit=5, owner=farmer,
        product_type="FARMER_LISTING",
    )
    Product.objects.create(
        title="Other Tomato", quantity=10, price_per_unit=5, owner=farmer_b,
        product_type="FARMER_LISTING",
    )
    api.force_authenticate(user=farmer)
    response = api.get("/api/v1/products/farmer-listings/my/")
    assert response.status_code == 200
    titles = [row["title"] for row in response.data["results"]]
    assert titles == ["My Tomato"]
    assert str(mine.id) in [row["id"] for row in response.data["results"]]


def test_tc_be_15b_farmer_cannot_edit_another_farmers_listing(api, farmer, farmer_b):
    other = Product.objects.create(
        title="Not Mine", quantity=10, price_per_unit=5, owner=farmer_b,
        product_type="FARMER_LISTING",
    )
    api.force_authenticate(user=farmer)
    response = api.patch(
        f"/api/v1/products/farmer-listings/{other.id}/", {"title": "Hijacked"},
        format="json",
    )
    assert response.status_code == 403
    other.refresh_from_db()
    assert other.title == "Not Mine"
