"""Super Admin governance and auth/profile tests (FR-SA-01..05, FR-UA-*, UC-01, UC-02)."""
import uuid

import pytest
from django.conf import settings

from notifications.models import Notification
from payments.models import PaymentStatus
from users.models import AccountStatus, AuditLog, PlatformSettings, Role, User

pytestmark = pytest.mark.django_db


def _payload(**overrides):
    body = {
        "email": "newfarmer@test.et",
        "full_name": "New Farmer",
        "phone": "+251911000000",
        "location": "Amhara",
        "role": "FARMER",
        "password": "Str0ngPass!23",
        "privacy_policy_accepted": True,
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# Registration (UC-01)
# ---------------------------------------------------------------------------
def test_registration_creates_a_pending_account(api, user_admin):
    response = api.post("/api/v1/auth/register/", _payload(), format="json")
    assert response.status_code == 201, response.data
    user = User.objects.get(email="newfarmer@test.et")
    assert user.status == AccountStatus.PENDING
    assert user.is_active is False
    assert user.role == Role.FARMER
    assert user.privacy_policy_accepted is True
    assert Notification.objects.filter(type="REGISTRATION", recipient=user_admin).exists()


def test_registration_requires_privacy_acceptance(api):
    response = api.post(
        "/api/v1/auth/register/", _payload(privacy_policy_accepted=False), format="json"
    )
    assert response.status_code == 400
    assert not User.objects.filter(email="newfarmer@test.et").exists()


def test_registration_rejects_duplicate_email(api):
    api.post("/api/v1/auth/register/", _payload(), format="json")
    response = api.post("/api/v1/auth/register/", _payload(), format="json")
    assert response.status_code == 400
    assert User.objects.filter(email="newfarmer@test.et").count() == 1


def test_registration_rejects_a_short_password(api):
    response = api.post("/api/v1/auth/register/", _payload(password="short"), format="json")
    assert response.status_code == 400
    assert not User.objects.filter(email="newfarmer@test.et").exists()


def test_registration_rejects_admin_self_appointment(api):
    response = api.post(
        "/api/v1/auth/register/", _payload(role="SUPER_ADMIN"), format="json"
    )
    assert response.status_code == 400
    assert not User.objects.filter(role=Role.SUPER_ADMIN).exists()


def test_registration_is_blocked_when_registration_is_closed(api):
    config = PlatformSettings.load()
    config.registration_open = False
    config.save()
    response = api.post("/api/v1/auth/register/", _payload(), format="json")
    assert response.status_code == 403
    assert response.data["error"] == "Registration is currently closed."


def test_registration_auto_approves_when_approval_is_disabled(api):
    config = PlatformSettings.load()
    config.require_approval = False
    config.save()
    response = api.post("/api/v1/auth/register/", _payload(), format="json")
    assert response.status_code == 201
    user = User.objects.get(email="newfarmer@test.et")
    assert user.status == AccountStatus.APPROVED
    assert user.is_active is True


# ---------------------------------------------------------------------------
# Login / refresh / logout (UC-02, doc 5.1.6)
# ---------------------------------------------------------------------------
def test_login_returns_access_token_and_refresh_cookie(api, farmer):
    response = api.post(
        "/api/v1/auth/login/",
        {"email": "farmer@test.et", "password": "demo1234"},
        format="json",
    )
    assert response.status_code == 200, response.data
    assert response.data["success"] is True
    assert response.data["access"]
    assert response.data["user"]["role"] == "FARMER"
    assert response.data["user"]["permissions"]
    cookie = response.cookies[settings.REFRESH_COOKIE_KEY]
    assert cookie.value
    assert cookie["httponly"] is True


def test_login_rejects_a_wrong_password(api, farmer):
    response = api.post(
        "/api/v1/auth/login/",
        {"email": "farmer@test.et", "password": "wrong-pass"},
        format="json",
    )
    assert response.status_code == 400


def test_pending_user_cannot_log_in(api, pending_user):
    """The state is only disclosed after the password is proven (no enumeration)."""
    wrong = api.post(
        "/api/v1/auth/login/",
        {"email": pending_user.email, "password": "not-the-password"},
        format="json",
    )
    assert wrong.status_code == 400
    assert "pending" not in str(wrong.data).lower()

    response = api.post(
        "/api/v1/auth/login/",
        {"email": pending_user.email, "password": "demo1234"},
        format="json",
    )
    assert response.status_code == 400
    assert "pending admin approval" in str(response.data).lower()
    pending_user.refresh_from_db()
    assert pending_user.is_active is False


def test_suspended_user_cannot_log_in(api, farmer):
    farmer.suspend()
    response = api.post(
        "/api/v1/auth/login/",
        {"email": "farmer@test.et", "password": "demo1234"},
        format="json",
    )
    assert response.status_code == 400


def test_refresh_issues_a_new_access_token(api, farmer):
    login = api.post(
        "/api/v1/auth/login/",
        {"email": "farmer@test.et", "password": "demo1234"},
        format="json",
    )
    client = api.__class__()
    client.cookies[settings.REFRESH_COOKIE_KEY] = login.cookies[
        settings.REFRESH_COOKIE_KEY
    ].value
    response = client.post("/api/v1/auth/token/refresh/", {}, format="json")
    assert response.status_code == 200
    assert response.data["access"]


def test_refresh_without_a_cookie_is_unauthorized(api):
    assert api.post("/api/v1/auth/token/refresh/", {}).status_code == 401


def test_logout_clears_the_refresh_cookie(api, farmer):
    response = api.post("/api/v1/auth/logout/", {})
    assert response.status_code == 200
    assert response.cookies[settings.REFRESH_COOKIE_KEY].value == ""


def test_me_returns_role_permissions(api, retailer):
    api.force_authenticate(user=retailer)
    response = api.get("/api/v1/auth/me/")
    assert response.status_code == 200
    assert response.data["user"]["email"] == "retailer@test.et"
    assert "product:discover_wholesaler" in response.data["permissions"]


def test_me_requires_authentication(api):
    response = api.get("/api/v1/auth/me/")
    assert response.status_code in (401, 403)


def test_profile_update_lets_users_change_contact_fields(api, farmer):
    api.force_authenticate(user=farmer)
    response = api.patch(
        "/api/v1/auth/profile/",
        {"phone": "+251911999999", "location": "Bahir Dar"},
        format="json",
    )
    assert response.status_code == 200
    farmer.refresh_from_db()
    assert farmer.phone == "+251911999999"
    assert farmer.location == "Bahir Dar"


def test_profile_update_never_escalates_the_role(api, farmer):
    """``role`` is not a profile field, so the payload is ignored, not applied."""
    api.force_authenticate(user=farmer)
    response = api.patch("/api/v1/auth/profile/", {"role": "SUPER_ADMIN"}, format="json")
    assert response.status_code == 200
    assert response.data["user"]["role"] == "FARMER"
    farmer.refresh_from_db()
    assert farmer.role == Role.FARMER
    assert farmer.status == AccountStatus.APPROVED


def test_announcement_endpoint_is_public(api):
    config = PlatformSettings.load()
    config.announcement = "Harvest festival on Friday."
    config.save()
    response = api.get("/api/v1/auth/announcement/")
    assert response.status_code == 200
    assert response.data["announcement"] == "Harvest festival on Friday."
    assert response.data["registration_open"] is True


# ---------------------------------------------------------------------------
# FR-SA-01 — cross-module data access
# ---------------------------------------------------------------------------
def test_super_admin_data_defaults_to_users(api, super_admin, farmer):
    api.force_authenticate(user=super_admin)
    response = api.get("/api/v1/superadmin/data/")
    assert response.status_code == 200
    assert response.data["resource"] == "users"
    assert any(row["email"] == "farmer@test.et" for row in response.data["results"])


@pytest.mark.parametrize(
    "resource", ["users", "products", "orders", "payments", "chat", "notifications"]
)
def test_super_admin_data_supports_every_resource(api, super_admin, resource, payment):
    api.force_authenticate(user=super_admin)
    response = api.get("/api/v1/superadmin/data/", {"resource": resource})
    assert response.status_code == 200
    assert response.data["resource"] == resource
    assert response.data["count"] >= (1 if resource == "payments" else 0)


def test_super_admin_data_rejects_unknown_resource(api, super_admin):
    api.force_authenticate(user=super_admin)
    assert api.get("/api/v1/superadmin/data/", {"resource": "secrets"}).status_code == 400


def test_super_admin_data_is_privileged(api, user_admin):
    api.force_authenticate(user=user_admin)
    assert api.get("/api/v1/superadmin/data/").status_code == 403


# ---------------------------------------------------------------------------
# FR-SA-02 — admin sub-role accounts
# ---------------------------------------------------------------------------
def test_super_admin_lists_only_admin_subrole_accounts(api, super_admin, user_admin, farmer):
    api.force_authenticate(user=super_admin)
    response = api.get("/api/v1/superadmin/accounts/")
    assert response.status_code == 200
    emails = {row["email"] for row in response.data["results"]}
    assert "useradmin@test.et" in emails
    assert "farmer@test.et" not in emails


def test_super_admin_creates_a_financial_manager(api, super_admin):
    api.force_authenticate(user=super_admin)
    response = api.post(
        "/api/v1/superadmin/accounts/",
        {
            "email": "newfm@test.et",
            "full_name": "New Finance",
            "role": "FINANCIAL_MANAGER",
            "password": "Str0ngPass!23",
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    created = User.objects.get(email="newfm@test.et")
    assert created.role == Role.FINANCIAL_MANAGER
    assert created.status == AccountStatus.APPROVED
    assert Notification.objects.filter(recipient=created, type="SYSTEM").exists()
    assert AuditLog.objects.filter(action="admin_account_created").exists()


def test_super_admin_cannot_create_a_super_admin(api, super_admin):
    api.force_authenticate(user=super_admin)
    response = api.post(
        "/api/v1/superadmin/accounts/",
        {"email": "rival@test.et", "full_name": "Rival", "role": "SUPER_ADMIN"},
        format="json",
    )
    assert response.status_code == 400
    assert not User.objects.filter(email="rival@test.et").exists()


def test_super_admin_deactivates_and_reinstates(api, super_admin, user_admin):
    api.force_authenticate(user=super_admin)
    response = api.post(f"/api/v1/superadmin/accounts/{user_admin.id}/deactivate/", {})
    assert response.status_code == 200
    user_admin.refresh_from_db()
    assert user_admin.status == AccountStatus.DEACTIVATED
    assert user_admin.is_active is False

    response = api.post(f"/api/v1/superadmin/accounts/{user_admin.id}/reinstate/", {})
    assert response.status_code == 200
    user_admin.refresh_from_db()
    assert user_admin.status == AccountStatus.APPROVED
    assert user_admin.is_active is True


def test_super_admin_cannot_deactivate_itself(api, super_admin):
    """The account list only holds admin sub-roles, so Super Admin is not even addressable."""
    api.force_authenticate(user=super_admin)
    response = api.post(f"/api/v1/superadmin/accounts/{super_admin.id}/deactivate/", {})
    assert response.status_code == 404
    super_admin.refresh_from_db()
    assert super_admin.status == AccountStatus.APPROVED
    assert super_admin.is_active is True


def test_account_search_and_status_filter(api, super_admin, user_admin, financial_manager):
    api.force_authenticate(user=super_admin)
    assert api.get("/api/v1/superadmin/accounts/", {"search": "Hana"}).data["count"] == 1
    assert api.get("/api/v1/superadmin/accounts/", {"status": "SUSPENDED"}).data["count"] == 0
    assert api.get("/api/v1/superadmin/accounts/", {"status": "ALL"}).data["count"] >= 2


# ---------------------------------------------------------------------------
# FR-SA-03 — decision override
# ---------------------------------------------------------------------------
def test_super_admin_approves_a_pending_user(api, super_admin, pending_user):
    api.force_authenticate(user=super_admin)
    response = api.post(
        f"/api/v1/superadmin/users/{pending_user.id}/override/",
        {"decision": "APPROVE"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["previous_status"] == AccountStatus.PENDING
    pending_user.refresh_from_db()
    assert pending_user.status == AccountStatus.APPROVED
    assert pending_user.is_active is True
    assert Notification.objects.filter(recipient=pending_user, type="APPROVAL").exists()


def test_super_admin_reverses_a_rejection(api, super_admin, pending_user):
    pending_user.reject("Documents were unreadable")
    api.force_authenticate(user=super_admin)
    response = api.post(
        f"/api/v1/superadmin/users/{pending_user.id}/override/",
        {"decision": "APPROVE", "reason": "Documents re-checked"},
        format="json",
    )
    assert response.status_code == 200
    pending_user.refresh_from_db()
    assert pending_user.status == AccountStatus.APPROVED
    audit = AuditLog.objects.filter(action="user_decision_overridden").first()
    assert "Documents re-checked" in audit.detail


def test_super_admin_suspends_and_reactivates(api, super_admin, farmer):
    api.force_authenticate(user=super_admin)
    assert api.post(
        f"/api/v1/superadmin/users/{farmer.id}/override/", {"decision": "SUSPEND"}, format="json"
    ).status_code == 200
    farmer.refresh_from_db()
    assert farmer.status == AccountStatus.SUSPENDED
    assert api.post(
        f"/api/v1/superadmin/users/{farmer.id}/override/", {"decision": "REACTIVATE"}, format="json"
    ).status_code == 200
    farmer.refresh_from_db()
    assert farmer.status == AccountStatus.APPROVED


def test_override_rejects_unknown_decisions(api, super_admin, farmer):
    api.force_authenticate(user=super_admin)
    response = api.post(
        f"/api/v1/superadmin/users/{farmer.id}/override/",
        {"decision": "EXPLODE"},
        format="json",
    )
    assert response.status_code == 400
    farmer.refresh_from_db()
    assert farmer.status == AccountStatus.APPROVED


def test_override_of_a_missing_user_is_404(api, super_admin):
    api.force_authenticate(user=super_admin)
    response = api.post(
        f"/api/v1/superadmin/users/{uuid.uuid4()}/override/",
        {"decision": "APPROVE"},
        format="json",
    )
    assert response.status_code == 404


def test_override_is_closed_to_user_admins(api, user_admin, pending_user):
    api.force_authenticate(user=user_admin)
    response = api.post(
        f"/api/v1/superadmin/users/{pending_user.id}/override/",
        {"decision": "APPROVE"},
        format="json",
    )
    assert response.status_code == 403
    pending_user.refresh_from_db()
    assert pending_user.status == AccountStatus.PENDING


def test_audit_log_lists_super_admin_decisions(api, super_admin, pending_user):
    api.force_authenticate(user=super_admin)
    api.post(
        f"/api/v1/superadmin/users/{pending_user.id}/override/",
        {"decision": "APPROVE"},
        format="json",
    )
    response = api.get("/api/v1/superadmin/audit/")
    assert response.status_code == 200
    assert response.data["count"] >= 1
    assert response.data["results"][0]["action"] == "user_decision_overridden"
    assert response.data["results"][0]["actor"] == super_admin.id
    assert response.data["results"][0]["actor_name"] == super_admin.full_name


# ---------------------------------------------------------------------------
# FR-SA-04 — settings and announcements
# ---------------------------------------------------------------------------
def test_settings_round_trip(api, super_admin):
    api.force_authenticate(user=super_admin)
    assert api.get("/api/v1/superadmin/settings/").data["settings"]["maintenance_mode"] is False
    response = api.patch(
        "/api/v1/superadmin/settings/",
        {"maintenance_mode": True, "require_approval": False},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["updated"]["maintenance_mode"] is True
    config = PlatformSettings.load()
    assert config.maintenance_mode is True
    assert config.updated_by == super_admin
    assert AuditLog.objects.filter(action="platform_settings_updated").exists()


def test_settings_patch_without_fields_is_rejected(api, super_admin):
    api.force_authenticate(user=super_admin)
    assert api.patch("/api/v1/superadmin/settings/", {}, format="json").status_code == 400


def test_announcement_broadcast_reaches_everyone(api, super_admin, farmer, wholesaler, user_admin):
    api.force_authenticate(user=super_admin)
    response = api.post(
        "/api/v1/superadmin/announcement/", {"message": "Maintenance on Sunday."}, format="json"
    )
    assert response.status_code == 201
    assert response.data["recipients"] == 4
    assert Notification.objects.filter(message="Maintenance on Sunday.").count() == 4
    assert PlatformSettings.load().announcement == "Maintenance on Sunday."


def test_announcement_requires_a_message(api, super_admin):
    api.force_authenticate(user=super_admin)
    response = api.post("/api/v1/superadmin/announcement/", {"message": "  "}, format="json")
    assert response.status_code == 400


def test_settings_are_privileged(api, financial_manager):
    api.force_authenticate(user=financial_manager)
    assert api.get("/api/v1/superadmin/settings/").status_code == 403
    assert api.post("/api/v1/superadmin/announcement/", {"message": "x"}).status_code == 403


# ---------------------------------------------------------------------------
# FR-SA-05 — system health
# ---------------------------------------------------------------------------
def test_system_health_reports_platform_counters(
    api, super_admin, payment, order, farmer_product, pending_user
):
    payment.status = PaymentStatus.VERIFIED
    payment.save()
    api.force_authenticate(user=super_admin)
    response = api.get("/api/v1/superadmin/health/")
    assert response.status_code == 200
    assert response.data["users"]["total"] == User.objects.count()
    assert response.data["users"]["pending"] == 1
    assert response.data["listings"]["active"] == 1
    assert response.data["transactions"]["payments_verified"] == 1
    assert float(response.data["transactions"]["order_value_total"]) == 1250
    assert response.data["api"]["websocket_paths"] == [
        "/ws/chat/{channel_id}/",
        "/ws/notifications/",
    ]


def test_system_health_is_privileged(api, farmer):
    api.force_authenticate(user=farmer)
    assert api.get("/api/v1/superadmin/health/").status_code == 403
