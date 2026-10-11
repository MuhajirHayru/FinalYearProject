from datetime import datetime, timezone as datetime_timezone

import pytest

from users.models import AccountStatus, Role, User

pytestmark = pytest.mark.django_db


def test_pending_queue_filters_created_date_range(api, user_admin):
    early = User.objects.create_user(
        email="pending-early@test.et",
        password="test-password",
        full_name="Early Pending",
        role=Role.FARMER,
        status=AccountStatus.PENDING,
    )
    in_range = User.objects.create_user(
        email="pending-in-range@test.et",
        password="test-password",
        full_name="In Range Pending",
        role=Role.WHOLESALER,
        status=AccountStatus.PENDING,
    )
    late = User.objects.create_user(
        email="pending-late@test.et",
        password="test-password",
        full_name="Late Pending",
        role=Role.RETAILER,
        status=AccountStatus.PENDING,
    )
    User.objects.filter(pk=early.pk).update(
        created_at=datetime(2025, 1, 1, tzinfo=datetime_timezone.utc)
    )
    User.objects.filter(pk=in_range.pk).update(
        created_at=datetime(2025, 1, 15, tzinfo=datetime_timezone.utc)
    )
    User.objects.filter(pk=late.pk).update(
        created_at=datetime(2025, 2, 1, tzinfo=datetime_timezone.utc)
    )
    api.force_authenticate(user=user_admin)

    response = api.get(
        "/api/v1/admin/pending-users/",
        {"created_from": "2025-01-10", "created_to": "2025-01-31"},
    )

    assert response.status_code == 200, response.data
    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == str(in_range.pk)


@pytest.mark.parametrize(
    "params",
    [
        {"created_from": "15-01-2025"},
        {"created_from": "2025-02-01", "created_to": "2025-01-01"},
    ],
)
def test_pending_queue_rejects_invalid_date_ranges(api, user_admin, params):
    api.force_authenticate(user=user_admin)

    response = api.get("/api/v1/admin/pending-users/", params)

    assert response.status_code == 400
