from uuid import uuid4

import pytest

from registrations.models import (
    AdministrativeLocation,
    LocationLevel,
    RegistrationFieldConfiguration,
    UserRegistration,
)
from users.models import AuditLog

pytestmark = pytest.mark.django_db


def test_super_admin_manages_parent_linked_locations_with_soft_deactivation(
    api, super_admin
):
    api.force_authenticate(user=super_admin)
    created_region = api.post(
        "/api/v1/superadmin/locations/",
        {
            "source_id": "managed-region",
            "name": "Managed Region",
            "level": LocationLevel.REGION,
            "parent": None,
            "alternative_names": [],
        },
        format="json",
    )
    assert created_region.status_code == 201, created_region.data
    region_id = created_region.data["id"]
    created_zone = api.post(
        "/api/v1/superadmin/locations/",
        {
            "source_id": "managed-zone",
            "name": "Managed Zone",
            "level": LocationLevel.ZONE,
            "parent": str(region_id),
            "alternative_names": [],
        },
        format="json",
    )
    assert created_zone.status_code == 201, created_zone.data

    invalid_parent = api.post(
        "/api/v1/superadmin/locations/",
        {
            "source_id": "invalid-woreda",
            "name": "Invalid Woreda",
            "level": LocationLevel.KEBELE,
            "parent": str(created_zone.data["id"]),
            "alternative_names": [],
        },
        format="json",
    )
    assert invalid_parent.status_code == 400

    cannot_deactivate_parent = api.delete(
        f"/api/v1/superadmin/locations/{region_id}/"
    )
    assert cannot_deactivate_parent.status_code == 400
    assert AdministrativeLocation.objects.get(pk=region_id).active

    api.delete(f"/api/v1/superadmin/locations/{created_zone.data['id']}/")
    api.delete(f"/api/v1/superadmin/locations/{region_id}/")
    assert not AdministrativeLocation.objects.get(pk=region_id).active
    assert AuditLog.objects.filter(
        actor=super_admin, action="administrative_location_deactivated"
    ).count() == 2


def test_only_super_admin_can_manage_registration_product_options(api, user_admin):
    api.force_authenticate(user=user_admin)

    response = api.post(
        "/api/v1/superadmin/product-types/",
        {"code": "managed-dragonfruit", "name": "Dragonfruit", "category": "Fruits"},
        format="json",
    )

    assert response.status_code == 403


def test_registration_product_options_are_unique_and_soft_deactivated(
    api, super_admin
):
    api.force_authenticate(user=super_admin)
    suffix = uuid4().hex
    product_name = f"Managed Crop {suffix}"
    product_code = f"managed-{suffix}"
    response = api.post(
        "/api/v1/superadmin/product-types/",
        {"code": product_code, "name": product_name, "category": "Fruits"},
        format="json",
    )
    assert response.status_code == 201, response.data
    product_id = response.data["id"]

    duplicate = api.post(
        "/api/v1/superadmin/product-types/",
        {
            "code": f"{product_code}-duplicate",
            "name": product_name.lower(),
            "category": "Fruits",
        },
        format="json",
    )
    invalid_category = api.post(
        "/api/v1/superadmin/product-types/",
        {"code": "managed-grain", "name": "Barley", "category": "Grains"},
        format="json",
    )
    assert duplicate.status_code == 400
    assert invalid_category.status_code == 400

    deleted = api.delete(f"/api/v1/superadmin/product-types/{product_id}/")
    assert deleted.status_code == 204
    options = api.get("/api/v1/registration/product-types/")
    assert product_id not in {row["id"] for row in options.data}


def test_registration_form_fields_are_role_scoped_and_backend_enforced(
    api, farmer, super_admin
):
    api.force_authenticate(user=farmer)
    response = api.get(
        "/api/v1/registration/form-fields/?stage=PROFILE&role=FARMER"
    )
    assert response.status_code == 200
    keys = {field["field_key"] for field in response.data["results"]}
    assert "date_of_birth" in keys
    assert "business_name" not in keys

    UserRegistration.objects.create(user=farmer)
    invalid_update = api.patch(
        "/api/v1/registration/me/",
        {"business_name": "Not applicable"},
        format="json",
    )
    assert invalid_update.status_code == 400

    api.force_authenticate(user=super_admin)
    config = RegistrationFieldConfiguration.objects.get(
        stage=RegistrationFieldConfiguration.Stage.PROFILE,
        field_key=RegistrationFieldConfiguration.FieldKey.LOCATION,
    )
    cannot_hide_required_location = api.patch(
        f"/api/v1/superadmin/registration-fields/{config.pk}/",
        {"required": False},
        format="json",
    )
    assert cannot_hide_required_location.status_code == 400
    assert config.required and config.visible


def test_registration_form_configuration_is_super_admin_only(api, user_admin):
    api.force_authenticate(user=user_admin)

    response = api.get("/api/v1/superadmin/registration-fields/")

    assert response.status_code == 403
