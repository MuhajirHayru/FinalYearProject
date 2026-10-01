"""User Admin queue and notification REST tests (FR-UA-01..05, FR-N-*)."""
import pytest

from notifications.models import Notification
from users.models import AccountStatus, AuditLog, Role, User

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# FR-UA-01 — approval queue
# ---------------------------------------------------------------------------
def test_pending_queue_lists_only_pending_accounts(api, user_admin, pending_user, farmer):
    api.force_authenticate(user=user_admin)
    response = api.get("/api/v1/admin/pending-users/")
    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["email"] == pending_user.email
    assert response.data["results"][0]["status"] == AccountStatus.PENDING


def test_pending_queue_filters_by_role_and_search(api, user_admin, pending_user):
    User.objects.create_user(
        email="pendingwholesale@test.et",
        password="demo1234",
        full_name="Pending Wholesale",
        role=Role.WHOLESALER,
        status=AccountStatus.PENDING,
    )
    api.force_authenticate(user=user_admin)
    assert api.get("/api/v1/admin/pending-users/", {"role": "WHOLESALER"}).data["count"] == 1
    assert api.get("/api/v1/admin/pending-users/", {"role": "FARMER"}).data["count"] == 1
    assert api.get("/api/v1/admin/pending-users/", {"search": "Wholesale"}).data["count"] == 1
    assert api.get("/api/v1/admin/pending-users/", {"ordering": "full_name"}).status_code == 200


def test_pending_queue_is_privileged(api, farmer, pending_user):
    api.force_authenticate(user=farmer)
    assert api.get("/api/v1/admin/pending-users/").status_code == 403
    assert api.get("/api/v1/admin/users/").status_code == 403


# ---------------------------------------------------------------------------
# FR-UA-02 / FR-UA-03 — approve, reject, suspend
# ---------------------------------------------------------------------------
def test_approve_unlocks_the_account(api, user_admin, pending_user):
    api.force_authenticate(user=user_admin)
    response = api.post(f"/api/v1/admin/users/{pending_user.id}/approve/", {})
    assert response.status_code == 200
    assert response.data["user"]["status"] == AccountStatus.APPROVED
    pending_user.refresh_from_db()
    assert pending_user.status == AccountStatus.APPROVED
    assert pending_user.is_active is True
    assert Notification.objects.filter(recipient=pending_user, type="APPROVAL").exists()
    assert AuditLog.objects.filter(action="user_approved", target=pending_user.email).exists()


def test_approved_user_can_now_log_in(api, user_admin, pending_user):
    api.force_authenticate(user=user_admin)
    api.post(f"/api/v1/admin/users/{pending_user.id}/approve/", {})
    response = api.post(
        "/api/v1/auth/login/",
        {"email": pending_user.email, "password": "demo1234"},
        format="json",
    )
    assert response.status_code == 200, response.data


def test_approving_twice_is_rejected(api, user_admin, pending_user):
    api.force_authenticate(user=user_admin)
    api.post(f"/api/v1/admin/users/{pending_user.id}/approve/", {})
    response = api.post(f"/api/v1/admin/users/{pending_user.id}/approve/", {})
    assert response.status_code == 400
    assert "already approved" in response.data["error"]


def test_reject_records_the_reason_and_notifies(api, user_admin, pending_user):
    api.force_authenticate(user=user_admin)
    response = api.post(
        f"/api/v1/admin/users/{pending_user.id}/reject/",
        {"reason": "Phone number could not be verified"},
        format="json",
    )
    assert response.status_code == 200
    pending_user.refresh_from_db()
    assert pending_user.status == AccountStatus.REJECTED
    assert pending_user.rejection_reason == "Phone number could not be verified"
    assert pending_user.is_active is False
    notification = Notification.objects.get(recipient=pending_user, type="REJECTION")
    assert "Phone number could not be verified" in notification.message


def test_rejecting_twice_is_rejected(api, user_admin, pending_user):
    api.force_authenticate(user=user_admin)
    api.post(f"/api/v1/admin/users/{pending_user.id}/reject/", {"reason": "x"})
    assert api.post(f"/api/v1/admin/users/{pending_user.id}/reject/", {}).status_code == 400


def test_user_admin_cannot_suspend_an_admin_account(api, user_admin, financial_manager):
    api.force_authenticate(user=user_admin)
    response = api.post(f"/api/v1/admin/users/{financial_manager.id}/suspend/", {})
    assert response.status_code == 403
    financial_manager.refresh_from_db()
    assert financial_manager.status == AccountStatus.APPROVED


def test_super_admin_may_suspend_a_financial_manager(api, super_admin, financial_manager):
    api.force_authenticate(user=super_admin)
    response = api.post(f"/api/v1/admin/users/{financial_manager.id}/suspend/", {})
    assert response.status_code == 200
    financial_manager.refresh_from_db()
    assert financial_manager.status == AccountStatus.SUSPENDED
    assert financial_manager.is_active is False


def test_suspend_toggles_back_to_approved(api, user_admin, farmer):
    api.force_authenticate(user=user_admin)
    assert "suspended" in api.post(f"/api/v1/admin/users/{farmer.id}/suspend/", {}).data["message"]
    farmer.refresh_from_db()
    assert farmer.status == AccountStatus.SUSPENDED
    assert "reinstated" in api.post(f"/api/v1/admin/users/{farmer.id}/suspend/", {}).data["message"]
    farmer.refresh_from_db()
    assert farmer.status == AccountStatus.APPROVED
    assert farmer.is_active is True


def test_user_admin_cannot_suspend_itself(api, user_admin):
    """Admin sub-role accounts are off limits to a User Admin, even their own."""
    api.force_authenticate(user=user_admin)
    response = api.post(f"/api/v1/admin/users/{user_admin.id}/suspend/", {})
    assert response.status_code == 403
    user_admin.refresh_from_db()
    assert user_admin.status == AccountStatus.APPROVED


def test_user_actions_on_a_missing_user_are_404(api, user_admin):
    import uuid

    api.force_authenticate(user=user_admin)
    assert api.post(f"/api/v1/admin/users/{uuid.uuid4()}/approve/", {}).status_code == 404


# ---------------------------------------------------------------------------
# FR-UA-03 — user directory
# ---------------------------------------------------------------------------
def test_user_directory_paginates_and_filters(api, user_admin, farmer, pending_user):
    api.force_authenticate(user=user_admin)
    assert api.get("/api/v1/admin/users/").data["count"] == 3
    assert api.get("/api/v1/admin/users/", {"role": "FARMER"}).data["count"] == 2
    assert api.get("/api/v1/admin/users/", {"status": "PENDING"}).data["count"] == 1
    assert api.get("/api/v1/admin/users/", {"search": "Amhara"}).data["count"] == 1


def test_user_directory_hides_passwords(api, user_admin, farmer):
    api.force_authenticate(user=user_admin)
    row = api.get("/api/v1/admin/users/").data["results"][0]
    assert "password" not in row
    assert set(row) >= {"id", "email", "full_name", "role", "status", "location"}


# ---------------------------------------------------------------------------
# FR-UA-04 — broadcast messages
# ---------------------------------------------------------------------------
def test_broadcast_to_a_role(api, user_admin, farmer, wholesaler, retailer):
    api.force_authenticate(user=user_admin)
    response = api.post(
        "/api/v1/admin/messages/",
        {"role": "FARMER", "message": "Market opens at 6am."},
        format="json",
    )
    assert response.status_code == 201
    assert response.data["recipients"] == 1
    assert Notification.objects.filter(recipient=farmer, message="Market opens at 6am.").exists()


def test_broadcast_to_individuals(api, user_admin, farmer, wholesaler):
    api.force_authenticate(user=user_admin)
    response = api.post(
        "/api/v1/admin/messages/",
        {"user_ids": [str(farmer.id), str(wholesaler.id)], "message": "Maintenance tonight."},
        format="json",
    )
    assert response.status_code == 201
    assert response.data["recipients"] == 2


def test_broadcast_requires_a_target(api, user_admin):
    api.force_authenticate(user=user_admin)
    assert api.post("/api/v1/admin/messages/", {"message": "hi"}).status_code == 400
    assert api.post(
        "/api/v1/admin/messages/", {"role": "FARMER", "message": "  "}, format="json"
    ).status_code == 400


def test_broadcast_is_privileged(api, farmer):
    api.force_authenticate(user=farmer)
    assert api.post(
        "/api/v1/admin/messages/", {"role": "FARMER", "message": "x"}, format="json"
    ).status_code == 403


# ---------------------------------------------------------------------------
# Notification REST surface
# ---------------------------------------------------------------------------
def test_notification_list_is_scoped_to_the_recipient(api, farmer, wholesaler):
    Notification.objects.create(recipient=farmer, type="SYSTEM", message="For you")
    Notification.objects.create(recipient=wholesaler, type="SYSTEM", message="Not for you")
    api.force_authenticate(user=farmer)
    response = api.get("/api/v1/notifications/")
    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["message"] == "For you"


def test_unread_count_and_mark_read(api, farmer):
    first = Notification.objects.create(recipient=farmer, type="SYSTEM", message="One")
    Notification.objects.create(recipient=farmer, type="SYSTEM", message="Two")
    api.force_authenticate(user=farmer)
    assert api.get("/api/v1/notifications/unread-count/").data["unread_count"] == 2
    assert api.post(f"/api/v1/notifications/{first.id}/mark-read/", {}).data["updated"] == 1
    assert api.get("/api/v1/notifications/unread-count/").data["unread_count"] == 1
    assert api.post("/api/v1/notifications/mark-all-read/", {}).data["updated"] == 1
    assert api.get("/api/v1/notifications/unread-count/").data["unread_count"] == 0


def test_cannot_mark_someone_elses_notification(api, farmer, wholesaler):
    theirs = Notification.objects.create(recipient=wholesaler, type="SYSTEM", message="Theirs")
    api.force_authenticate(user=farmer)
    assert api.post(f"/api/v1/notifications/{theirs.id}/mark-read/", {}).data["updated"] == 0
    theirs.refresh_from_db()
    assert theirs.is_read is False


def test_notifications_require_authentication(api):
    assert api.get("/api/v1/notifications/").status_code in (401, 403)
