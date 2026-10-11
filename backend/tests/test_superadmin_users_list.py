from datetime import date

import pytest

from users.models import AccountStatus, Role, User

pytestmark = pytest.mark.django_db


def test_super_admin_user_directory_paginates_beyond_previous_limit(
    api, super_admin
):
    User.objects.bulk_create(
        [
            User(
                full_name=f"Directory User {index}",
                email=f"directory-user-{index}@test.et",
                role=Role.FARMER,
                status=AccountStatus.APPROVED,
            )
            for index in range(201)
        ]
    )
    api.force_authenticate(user=super_admin)

    first_page = api.get("/api/v1/superadmin/users/")
    last_page = api.get("/api/v1/superadmin/users/", {"page": 11})

    assert first_page.status_code == 200, first_page.data
    assert first_page.data["count"] == 202
    assert len(first_page.data["results"]) == 20
    assert last_page.status_code == 200, last_page.data
    assert last_page.data["count"] == 202
    assert len(last_page.data["results"]) == 2
    assert last_page.data["next"] is None


def test_super_admin_user_directory_filters_server_side(api, super_admin):
    User.objects.create_user(
        email="filter-target@test.et",
        password="test-password",
        full_name="Filter Target",
        role=Role.WHOLESALER,
        status=AccountStatus.SUSPENDED,
    )
    api.force_authenticate(user=super_admin)

    response = api.get(
        "/api/v1/superadmin/users/",
        {"role": Role.WHOLESALER, "status": AccountStatus.SUSPENDED, "search": "target"},
    )

    assert response.status_code == 200, response.data
    assert response.data["count"] == 1
    assert response.data["results"][0]["email"] == "filter-target@test.et"


def test_super_admin_user_directory_validates_date_filters(api, super_admin):
    api.force_authenticate(user=super_admin)

    malformed = api.get(
        "/api/v1/superadmin/users/", {"created_from": "not-a-date"}
    )
    reversed_range = api.get(
        "/api/v1/superadmin/users/",
        {"created_from": date(2026, 2, 1).isoformat(), "created_to": date(2026, 1, 1).isoformat()},
    )

    assert malformed.status_code == 400
    assert reversed_range.status_code == 400
