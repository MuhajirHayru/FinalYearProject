"""Super Admin governance and auth/profile tests (FR-SA-01..05, FR-UA-*, UC-01, UC-02)."""
import uuid
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from django.core import mail
from django.core.cache import cache
from django.conf import settings
from django.utils import timezone
from django.test import override_settings

from notifications.models import Notification
from payments.models import PaymentStatus
from registrations.models import RegistrationStatus, UserRegistration
from users.models import AccountStatus, AuditLog, PlatformSettings, Role, User

pytestmark = pytest.mark.django_db


@pytest.fixture
def isolated_login_throttle():
    cache.clear()
    yield
    cache.clear()


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
def test_registration_creates_a_pending_account_and_completion_draft(api, user_admin):
    response = api.post("/api/v1/auth/register/", _payload(), format="json")
    assert response.status_code == 201, response.data
    user = User.objects.get(email="newfarmer@test.et")
    assert user.status == AccountStatus.PENDING
    assert user.is_active is False
    assert user.role == Role.FARMER
    assert user.privacy_policy_accepted is True
    assert response.data["completion_token"]
    assert UserRegistration.objects.get(user=user).status == RegistrationStatus.DRAFT
    assert not Notification.objects.filter(type="REGISTRATION", recipient=user_admin).exists()


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
    assert response.data["attempts_remaining"] == 2
    assert response.data["max_attempts"] == 3
    farmer.refresh_from_db()
    assert farmer.failed_login_attempts == 1


def test_locked_login_does_not_verify_password(
    api, farmer, monkeypatch, isolated_login_throttle
):
    farmer.locked_until = timezone.now() + timedelta(minutes=5)
    farmer.save(update_fields=["locked_until"])

    def unexpected_password_check(*args, **kwargs):
        raise AssertionError("Password hashing must be skipped for locked accounts.")

    monkeypatch.setattr(User, "check_password", unexpected_password_check)
    response = api.post(
        "/api/v1/auth/login/",
        {"email": farmer.email, "password": "incorrect"},
        format="json",
    )

    assert response.status_code == 400
    assert "temporarily locked" in str(response.data).lower()


def test_password_hash_check_runs_outside_the_account_lock(
    api, farmer, monkeypatch, isolated_login_throttle
):
    from contextlib import contextmanager
    from users.serializers import transaction as serializer_transaction

    original_check_password = User.check_password
    original_atomic = serializer_transaction.atomic
    lock_active = False
    observed_transactions = []

    @contextmanager
    def observe_atomic(*args, **kwargs):
        nonlocal lock_active
        with original_atomic(*args, **kwargs):
            lock_active = True
            try:
                yield
            finally:
                lock_active = False

    def inspect_transaction(user, raw_password):
        observed_transactions.append(lock_active)
        return original_check_password(user, raw_password)

    monkeypatch.setattr(serializer_transaction, "atomic", observe_atomic)
    monkeypatch.setattr(User, "check_password", inspect_transaction)
    response = api.post(
        "/api/v1/auth/login/",
        {"email": farmer.email, "password": "incorrect"},
        format="json",
    )

    assert response.status_code == 400
    assert observed_transactions == [False]


def test_login_does_not_repeat_check_after_password_hash_upgrade(
    api, farmer, monkeypatch, isolated_login_throttle
):
    check_count = 0

    def upgrade_password_hash(user, raw_password):
        nonlocal check_count
        check_count += 1
        if check_count > 1:
            raise AssertionError("An upgraded password hash must not be checked twice.")
        user.password = "simulated-upgraded-password-hash"
        user.save(update_fields=["password"])
        return True

    monkeypatch.setattr(User, "check_password", upgrade_password_hash)
    response = api.post(
        "/api/v1/auth/login/",
        {"email": farmer.email, "password": "demo1234"},
        format="json",
    )

    assert response.status_code == 200, response.data
    assert check_count == 1


def test_failed_login_reloads_counter_after_hash_verification(
    api, farmer, monkeypatch, isolated_login_throttle
):
    farmer.failed_login_attempts = 1
    farmer.save(update_fields=["failed_login_attempts"])

    def complete_competing_failure(user, raw_password):
        User.objects.filter(pk=user.pk).update(failed_login_attempts=2)
        return False

    monkeypatch.setattr(User, "check_password", complete_competing_failure)
    response = api.post(
        "/api/v1/auth/login/",
        {"email": farmer.email, "password": "incorrect"},
        format="json",
    )

    assert response.status_code == 400
    farmer.refresh_from_db()
    assert farmer.failed_login_attempts == 0
    assert farmer.locked_until is not None


def test_login_after_lockout_expiration_resets_lock_state(
    api, farmer, isolated_login_throttle
):
    farmer.failed_login_attempts = 2
    farmer.locked_until = timezone.now() - timedelta(seconds=1)
    farmer.save(update_fields=["failed_login_attempts", "locked_until"])

    response = api.post(
        "/api/v1/auth/login/",
        {"email": farmer.email, "password": "demo1234"},
        format="json",
    )

    assert response.status_code == 200
    farmer.refresh_from_db()
    assert farmer.failed_login_attempts == 0
    assert farmer.locked_until is None


def test_login_locks_after_configured_consecutive_failures(api, farmer):
    policy = PlatformSettings.load()
    policy.max_failed_login_attempts = 3
    policy.lockout_duration_minutes = 180
    policy.save()

    for _ in range(3):
        response = api.post(
            "/api/v1/auth/login/",
            {"email": farmer.email, "password": "incorrect"},
            format="json",
        )
        assert response.status_code == 400

    farmer.refresh_from_db()
    assert farmer.failed_login_attempts == 0
    assert farmer.locked_until is not None
    assert farmer.locked_until > timezone.now() + timedelta(minutes=179)
    assert AuditLog.objects.filter(
        action="account_login_locked", target=str(farmer.pk)
    ).exists()

    locked = api.post(
        "/api/v1/auth/login/",
        {"email": farmer.email, "password": "incorrect"},
        format="json",
    )
    assert locked.status_code == 400
    assert "temporarily locked" in str(locked.data).lower()
    assert locked.data["attempts_remaining"] == 0
    assert locked.data["retry_after_seconds"] > 0


def test_login_uses_latest_lockout_policy(api, farmer, super_admin):
    api.force_authenticate(user=super_admin)
    saved = api.patch(
        "/api/v1/superadmin/settings/",
        {
            "max_failed_login_attempts": 2,
            "lockout_duration_minutes": 30,
            "reason": "Reduce account takeover risk",
        },
        format="json",
    )
    assert saved.status_code == 200, saved.data

    api.force_authenticate(user=None)
    first_attempt = api.post(
        "/api/v1/auth/login/",
        {"email": farmer.email, "password": "incorrect"},
        format="json",
    )
    assert first_attempt.data["attempts_remaining"] == 1
    second_attempt = api.post(
            "/api/v1/auth/login/",
            {"email": farmer.email, "password": "incorrect"},
            format="json",
        )
    assert second_attempt.data["attempts_remaining"] == 0
    assert second_attempt.data["retry_after_seconds"] > 0

    farmer.refresh_from_db()
    assert farmer.locked_until is not None
    assert farmer.locked_until > timezone.now() + timedelta(minutes=29)


def test_successful_login_resets_failed_attempt_counter(api, farmer):
    api.post(
        "/api/v1/auth/login/",
        {"email": farmer.email, "password": "incorrect"},
        format="json",
    )
    farmer.refresh_from_db()
    assert farmer.failed_login_attempts == 1

    response = api.post(
        "/api/v1/auth/login/",
        {"email": farmer.email, "password": "demo1234"},
        format="json",
    )
    assert response.status_code == 200
    farmer.refresh_from_db()
    assert farmer.failed_login_attempts == 0
    assert farmer.locked_until is None


def test_super_admin_can_unlock_account_and_audit_reason(api, farmer, super_admin):
    farmer.failed_login_attempts = 3
    farmer.locked_until = timezone.now() + timedelta(hours=3)
    farmer.save(update_fields=["failed_login_attempts", "locked_until"])
    api.force_authenticate(user=super_admin)

    response = api.post(
        f"/api/v1/superadmin/users/{farmer.pk}/unlock-login/",
        {"reason": "Verified the account holder by phone"},
        format="json",
    )

    assert response.status_code == 200, response.data
    farmer.refresh_from_db()
    assert farmer.failed_login_attempts == 0
    assert farmer.locked_until is None
    audit = AuditLog.objects.get(
        action="account_login_unlocked",
        target=str(farmer.pk),
    )
    assert "Verified the account holder by phone" in audit.detail


def test_login_unlock_requires_reason_and_active_lock(api, farmer, super_admin):
    api.force_authenticate(user=super_admin)
    missing_reason = api.post(
        f"/api/v1/superadmin/users/{farmer.pk}/unlock-login/",
        {},
        format="json",
    )
    assert missing_reason.status_code == 400

    response = api.post(
        f"/api/v1/superadmin/users/{farmer.pk}/unlock-login/",
        {"reason": "No active lock"},
        format="json",
    )
    assert response.status_code == 409


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_password_reset_email_is_generic_and_one_time(api, farmer):
    request = api.post(
        "/api/v1/auth/password-reset/request/",
        {"channel": "email", "identifier": farmer.email},
        format="json",
    )
    assert request.status_code == 202
    assert "if an account matches" in request.data["message"].lower()
    assert len(mail.outbox) == 1
    reset_url = next(
        part
        for part in mail.outbox[0].body.split()
        if "/reset-password?" in part
    )
    query = parse_qs(urlparse(reset_url).query)

    response = api.post(
        "/api/v1/auth/password-reset/confirm/",
        {
            "uid": query["uid"][0],
            "token": query["token"][0],
            "new_password": "New-Secure-Password!42",
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    farmer.refresh_from_db()
    assert farmer.check_password("New-Secure-Password!42")
    assert farmer.password_changed_at is not None
    assert AuditLog.objects.filter(
        action="password_reset_completed", target=str(farmer.pk)
    ).exists()

    reused = api.post(
        "/api/v1/auth/password-reset/confirm/",
        {
            "uid": query["uid"][0],
            "token": query["token"][0],
            "new_password": "Another-Secure-Password!42",
        },
        format="json",
    )
    assert reused.status_code == 400


def test_password_reset_does_not_disclose_unknown_accounts(api):
    response = api.post(
        "/api/v1/auth/password-reset/request/",
        {"channel": "email", "identifier": "missing@example.et"},
        format="json",
    )
    assert response.status_code == 202
    assert "if an account matches" in response.data["message"].lower()


def test_password_reset_sms_uses_on_file_number(api, farmer, monkeypatch):
    farmer.phone = "+251911000001"
    farmer.save(update_fields=["phone"])
    delivered = []

    def capture_delivery(user, channel, reset_url):
        delivered.append((user.pk, channel, reset_url))

    monkeypatch.setattr("users.views.send_password_reset", capture_delivery)
    response = api.post(
        "/api/v1/auth/password-reset/request/",
        {"channel": "sms", "identifier": farmer.phone},
        format="json",
    )

    assert response.status_code == 202
    assert delivered and delivered[0][0] == farmer.pk
    assert delivered[0][1] == "sms"
    assert "/reset-password?" in delivered[0][2]


def test_password_change_revokes_existing_access_and_refresh_tokens(api, farmer):
    login = api.post(
        "/api/v1/auth/login/",
        {"email": farmer.email, "password": "demo1234"},
        format="json",
    )
    old_access = login.data["access"]
    old_refresh = login.cookies[settings.REFRESH_COOKIE_KEY].value

    api.force_authenticate(user=None)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {old_access}")
    changed = api.post(
        "/api/v1/auth/password/change/",
        {
            "current_password": "demo1234",
            "new_password": "Changed-Secure-Password!42",
        },
        format="json",
    )
    assert changed.status_code == 200, changed.data

    denied_access = api.get("/api/v1/auth/me/")
    assert denied_access.status_code == 401
    api.credentials()
    api.cookies[settings.REFRESH_COOKIE_KEY] = old_refresh
    denied_refresh = api.post("/api/v1/auth/token/refresh/", {}, format="json")
    assert denied_refresh.status_code == 401

    new_login = api.post(
        "/api/v1/auth/login/",
        {"email": farmer.email, "password": "Changed-Secure-Password!42"},
        format="json",
    )
    assert new_login.status_code == 200, new_login.data


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
        {"phone": "+251911999999"},
        format="json",
    )
    assert response.status_code == 200
    farmer.refresh_from_db()
    assert farmer.phone == "+251911999999"


def test_profile_update_requires_configured_location_selection(api, farmer):
    api.force_authenticate(user=farmer)
    response = api.patch(
        "/api/v1/auth/profile/",
        {"location": "Bahir Dar"},
        format="json",
    )
    assert response.status_code == 400
    assert "location" in response.data["error"]


def test_profile_update_obeys_post_approval_field_configuration(api, farmer):
    from registrations.models import RegistrationFieldConfiguration

    phone_field = RegistrationFieldConfiguration.objects.get(
        stage=RegistrationFieldConfiguration.Stage.PROFILE,
        field_key="phone",
    )
    phone_field.editable_after_approval = False
    phone_field.save(update_fields=["editable_after_approval"])
    api.force_authenticate(user=farmer)
    response = api.patch(
        "/api/v1/auth/profile/",
        {"phone": "+251911999999"},
        format="json",
    )
    assert response.status_code == 400
    assert "phone" in response.data["error"]


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
    assert response.data["results"][0]["actor_role"] == Role.SUPER_ADMIN


def test_audit_log_filters_registration_status(api, super_admin, pending_user):
    UserRegistration.objects.create(
        user=pending_user,
        status=RegistrationStatus.SUBMITTED,
    )
    AuditLog.objects.create(
        actor=super_admin,
        action="registration_reviewed",
        target=pending_user.email,
    )
    AuditLog.objects.create(
        actor=super_admin,
        action="platform_settings_updated",
        target="platform",
    )

    api.force_authenticate(user=super_admin)
    response = api.get(
        "/api/v1/superadmin/audit/",
        {"registration_status": RegistrationStatus.SUBMITTED},
    )

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["target"] == pending_user.email


def test_audit_log_rejects_invalid_filter_values(api, super_admin):
    api.force_authenticate(user=super_admin)
    response = api.get(
        "/api/v1/superadmin/audit/",
        {"registration_status": "UNKNOWN"},
    )

    assert response.status_code == 400
    assert "registration_status" in response.data["error"]


# ---------------------------------------------------------------------------
# FR-SA-04 — settings and announcements
# ---------------------------------------------------------------------------
def test_settings_round_trip(api, super_admin):
    api.force_authenticate(user=super_admin)
    current = api.get("/api/v1/superadmin/settings/").data["settings"]
    assert current["maintenance_mode"] is False
    assert current["max_failed_login_attempts"] == 3
    assert current["lockout_duration_minutes"] == 180
    response = api.patch(
        "/api/v1/superadmin/settings/",
        {
            "maintenance_mode": True,
            "require_approval": False,
            "reason": "Scheduled infrastructure maintenance",
        },
        format="json",
    )
    assert response.status_code == 200
    assert response.data["updated"]["maintenance_mode"] is True
    config = PlatformSettings.load()
    assert config.maintenance_mode is True
    assert config.updated_by == super_admin
    assert AuditLog.objects.filter(action="platform_settings_updated").exists()
    entry = AuditLog.objects.get(action="platform_settings_updated")
    assert '"previous"' in entry.detail
    assert "Scheduled infrastructure maintenance" in entry.detail


def test_security_settings_require_reason_and_validate_ranges(api, super_admin):
    api.force_authenticate(user=super_admin)
    missing_reason = api.patch(
        "/api/v1/superadmin/settings/",
        {"max_failed_login_attempts": 5},
        format="json",
    )
    assert missing_reason.status_code == 400
    assert "reason" in missing_reason.data["error"]

    invalid = api.patch(
        "/api/v1/superadmin/settings/",
        {
            "lockout_duration_minutes": 10081,
            "reason": "Invalid test",
        },
        format="json",
    )
    assert invalid.status_code == 400


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
