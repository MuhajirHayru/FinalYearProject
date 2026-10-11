import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from notifications.models import Notification
from products.models import Category
from registrations.models import (
    AdministratorScope,
    AdministrativeLocation,
    AgriculturalProductType,
    LocationLevel,
    RegistrationDocument,
    RegistrationReview,
    RegistrationStatus,
    UserRegistration,
)
from registrations.services import can_assign_admin_scope
from users.models import AccountStatus, AuditLog, Role, User

pytestmark = pytest.mark.django_db


def _create_registration(api, *, email="registration-farmer@test.et"):
    response = api.post(
        "/api/v1/auth/register/",
        {
            "email": email,
            "full_name": "Registration Farmer",
            "phone": "+251911123456",
            "role": Role.FARMER,
            "password": "Str0ngPass!23",
            "privacy_policy_accepted": True,
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    user = User.objects.get(email=email)
    return user, response.data["completion_token"]


@pytest.mark.parametrize(
    ("role", "email"),
    [
        (Role.FARMER, "registration-create-farmer@test.et"),
        (Role.WHOLESALER, "registration-create-wholesaler@test.et"),
        (Role.RETAILER, "registration-create-retailer@test.et"),
    ],
)
def test_each_marketplace_role_creates_one_linked_registration_draft(api, role, email):
    response = api.post(
        "/api/v1/auth/register/",
        {
            "email": email,
            "full_name": "New Marketplace User",
            "phone": "+251911123456",
            "role": role,
            "password": "Str0ngPass!23",
            "privacy_policy_accepted": True,
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    user = User.objects.get(email=email)
    registration = UserRegistration.objects.get(user=user)
    assert response.data["completion_token"]
    assert user.role == role
    assert user.status == AccountStatus.PENDING
    assert user.is_active is False
    assert registration.status == RegistrationStatus.DRAFT
    assert UserRegistration.objects.filter(user_id=user.pk).count() == 1


def _location(name, source_id, parent=None, level=LocationLevel.REGION):
    return AdministrativeLocation.objects.create(
        name=name,
        source_id=source_id,
        parent=parent,
        level=level,
    )


def _submitted_registration(user, location, license_type="FARMER_LICENSE"):
    registration = UserRegistration.objects.create(
        user=user,
        location=location,
        status=RegistrationStatus.SUBMITTED,
    )
    document = RegistrationDocument.objects.create(
        registration=registration,
        document_type=license_type,
        original_filename=f"{license_type.lower()}.pdf",
        file=SimpleUploadedFile(
            f"{license_type.lower()}.pdf",
            b"%PDF-1.4\nlicense test",
            content_type="application/pdf",
        ),
    )
    return registration, document


def test_completion_credential_is_limited_and_draft_persists(api):
    user, token = _create_registration(api)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    response = api.get("/api/v1/registration/me/")
    assert response.status_code == 200, response.data
    assert response.data["status"] == RegistrationStatus.DRAFT

    region = _location("Verified Region", "test-region")
    product = AgriculturalProductType.objects.create(
        code="test-tomato",
        name="Test Registration Tomato",
        category=Category.VEGETABLES,
    )
    response = api.patch(
        "/api/v1/registration/me/",
        {
            "date_of_birth": "1990-01-01",
            "sex": "PREFER_NOT_TO_SAY",
            "location": str(region.pk),
            "product_selections": [
                {"product_type": str(product.pk), "intent": "PRODUCES"}
            ],
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    user.refresh_from_db()
    registration = UserRegistration.objects.get(user=user)
    assert registration.location == region
    assert list(registration.product_types.values_list("name", flat=True)) == ["Test Registration Tomato"]
    assert user.status == AccountStatus.PENDING
    assert user.is_active is False

    marketplace_response = api.get("/api/v1/auth/me/")
    assert marketplace_response.status_code in (401, 403)


def test_registration_product_catalog_only_exposes_vegetables_and_fruits(api):
    vegetable = AgriculturalProductType.objects.create(
        code="registration-cabbage",
        name="Registration Cabbage",
        category=Category.VEGETABLES,
    )
    root_crop = AgriculturalProductType.objects.create(
        code="registration-potato",
        name="Registration Potato",
        category=Category.ROOT_CROPS,
    )
    fruit = AgriculturalProductType.objects.create(
        code="registration-mango",
        name="Registration Mango",
        category=Category.FRUITS,
    )
    grain = AgriculturalProductType.objects.create(
        code="registration-teff",
        name="Registration Teff",
        category=Category.GRAINS,
    )

    response = api.get("/api/v1/registration/product-types/")

    assert response.status_code == 200, response.data
    returned_ids = {item["id"] for item in response.data}
    assert {str(vegetable.pk), str(root_crop.pk), str(fruit.pk)} <= returned_ids
    assert str(grain.pk) not in returned_ids


def test_registration_rejects_product_interest_outside_allowed_categories(api):
    user, token = _create_registration(api)
    grain = AgriculturalProductType.objects.create(
        code="registration-invalid-grain",
        name="Registration Invalid Grain",
        category=Category.GRAINS,
    )
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    response = api.patch(
        "/api/v1/registration/me/",
        {
            "product_selections": [
                {"product_type": str(grain.pk), "intent": "PRODUCES"}
            ],
        },
        format="json",
    )

    assert response.status_code == 400, response.data
    registration = UserRegistration.objects.get(user=user)
    assert not registration.product_selections.exists()


def test_submission_requires_verified_reference_data_and_license_then_review(api, user_admin):
    user, token = _create_registration(api, email="submit-farmer@test.et")
    region = _location("Verified Region", "submit-region")
    product = AgriculturalProductType.objects.create(
        code="submit-tomato",
        name="Submitted Registration Tomato",
        category=Category.VEGETABLES,
    )
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    api.patch(
        "/api/v1/registration/me/",
        {
            "date_of_birth": "1990-01-01",
            "sex": "FEMALE",
            "location": str(region.pk),
            "product_selections": [
                {"product_type": str(product.pk), "intent": "PRODUCES"}
            ],
        },
        format="json",
    )
    upload = SimpleUploadedFile("farm-license.pdf", b"%PDF-1.4\nlicense test", content_type="application/pdf")
    response = api.post(
        "/api/v1/registration/me/documents/",
        {"file": upload},
        format="multipart",
    )
    assert response.status_code == 201, response.data
    document_id = response.data["id"]
    document = RegistrationDocument.objects.get(pk=document_id)
    with pytest.raises(ValueError, match="no public URL"):
        document.file.url

    assert not Notification.objects.filter(
        recipient=user_admin, type="REGISTRATION"
    ).exists()
    response = api.post("/api/v1/registration/me/submit/", {"confirm": True}, format="json")
    assert response.status_code == 200, response.data
    registration = UserRegistration.objects.get(user=user)
    assert registration.status == RegistrationStatus.SUBMITTED
    assert registration.submitted_at is not None
    assert Notification.objects.filter(recipient=user, type="REGISTRATION").exists()
    assert Notification.objects.filter(recipient=user_admin, type="REGISTRATION").exists()

    api.force_authenticate(user=user_admin)
    response = api.post(
        f"/api/v1/admin/registration-documents/{document_id}/verification/",
        {"verified": True},
        format="json",
    )
    assert response.status_code == 200, response.data
    response = api.post(
        f"/api/v1/admin/registrations/{registration.pk}/decision/",
        {"action": "APPROVE"},
        format="json",
    )
    assert response.status_code == 200, response.data
    user.refresh_from_db()
    registration.refresh_from_db()
    assert user.status == AccountStatus.APPROVED
    assert user.is_active is True
    assert registration.status == RegistrationStatus.APPROVED
    assert RegistrationReview.objects.filter(
        registration=registration,
        action=RegistrationReview.Action.APPROVED,
    ).exists()


def test_registration_review_list_and_decision_are_restricted_to_admin_scope(api, user_admin):
    north = _location("North", "scope-north")
    north_child = _location(
        "North District",
        "scope-north-district",
        parent=north,
        level=LocationLevel.WOREDA,
    )
    south = _location("South", "scope-south")
    visible_user = User.objects.create_user(
        email="visible-registration@test.et",
        password="Str0ngPass!23",
        full_name="Visible Farmer",
        phone="+251911000001",
        role=Role.FARMER,
        status=AccountStatus.PENDING,
    )
    visible = UserRegistration.objects.create(
        user=visible_user,
        location=north_child,
        status=RegistrationStatus.SUBMITTED,
    )
    hidden_user = User.objects.create_user(
        email="hidden-registration@test.et",
        password="Str0ngPass!23",
        full_name="Hidden Farmer",
        phone="+251911000002",
        role=Role.FARMER,
        status=AccountStatus.PENDING,
    )
    UserRegistration.objects.create(
        user=hidden_user,
        location=south,
        status=RegistrationStatus.SUBMITTED,
    )
    scope = AdministratorScope.objects.get(user=user_admin)
    scope.level = AdministratorScope.Level.LOCATION
    scope.location = north
    scope.save()
    user_admin.refresh_from_db()
    api.force_authenticate(user=user_admin)

    response = api.get("/api/v1/admin/registrations/")
    assert response.status_code == 200, response.data
    visible_ids = {row["id"] for row in response.data["results"]}
    assert str(visible.pk) in visible_ids
    hidden_registration = UserRegistration.objects.get(user=hidden_user)
    assert str(hidden_registration.pk) not in visible_ids
    response = api.post(
        f"/api/v1/admin/registrations/{visible.pk}/decision/",
        {"action": "REJECT", "reason": "Missing supporting detail."},
        format="json",
    )
    assert response.status_code == 200, response.data

    response = api.post(
        f"/api/v1/admin/registrations/{hidden_registration.pk}/decision/",
        {"action": "REJECT", "reason": "Unauthorized attempt."},
        format="json",
    )
    assert response.status_code == 404


def test_user_admin_audit_log_is_filtered_to_assigned_geography(api, user_admin):
    north = _location("Audit North", "audit-north")
    north_child = _location(
        "Audit North Woreda",
        "audit-north-woreda",
        parent=north,
        level=LocationLevel.WOREDA,
    )
    south = _location("Audit South", "audit-south")
    scoped_users = []
    for email, location in (
        ("audit-visible@test.et", north_child),
        ("audit-hidden@test.et", south),
    ):
        user = User.objects.create_user(
            email=email,
            password="TestPass123!",
            full_name=email.split("@")[0],
            role=Role.FARMER,
            status=AccountStatus.PENDING,
        )
        UserRegistration.objects.create(
            user=user,
            location=location,
            status=RegistrationStatus.SUBMITTED,
        )
        scoped_users.append(user)
        AuditLog.objects.create(
            action="registration_reviewed",
            target=email,
        )

    scope = AdministratorScope.objects.get(user=user_admin)
    scope.level = AdministratorScope.Level.LOCATION
    scope.location = north
    scope.save()
    api.force_authenticate(user=user_admin)

    response = api.get("/api/v1/superadmin/audit/")

    assert response.status_code == 200, response.data
    assert [row["target"] for row in response.data["results"]] == [
        scoped_users[0].email
    ]


def test_user_admin_uses_persisted_role_license_status_for_approval(api, user_admin):
    region = _location("Approval Region", "approval-region")
    user = User.objects.create_user(
        email="approval-flow@test.et",
        password="Str0ngPass!23",
        full_name="Approval Farmer",
        phone="+251911000003",
        role=Role.FARMER,
        status=AccountStatus.PENDING,
    )
    registration, document = _submitted_registration(user, region)
    api.force_authenticate(user=user_admin)

    pending_users = api.get("/api/v1/admin/pending-users/")
    assert pending_users.status_code == 200
    assert str(user.pk) not in {row["id"] for row in pending_users.data["results"]}
    registrations = api.get("/api/v1/admin/registrations/")
    assert registrations.status_code == 200
    assert str(registration.pk) in {row["id"] for row in registrations.data["results"]}

    response = api.post(
        f"/api/v1/admin/registration-documents/{document.pk}/verification/",
        {"verified": True},
        format="json",
    )
    assert response.status_code == 200, response.data
    document.refresh_from_db()
    assert document.verification_status == RegistrationDocument.VerificationStatus.VERIFIED
    assert document.verified_by == user_admin
    assert document.verified_at is not None

    response = api.post(f"/api/v1/admin/users/{user.pk}/approve/")
    assert response.status_code == 200, response.data
    user.refresh_from_db()
    registration.refresh_from_db()
    assert user.status == AccountStatus.APPROVED
    assert registration.status == RegistrationStatus.APPROVED


def test_verified_unrelated_license_type_cannot_approve_farmer(api, user_admin):
    region = _location("License Region", "license-region")
    user = User.objects.create_user(
        email="wrong-license-type@test.et",
        password="Str0ngPass!23",
        full_name="License Farmer",
        phone="+251911000004",
        role=Role.FARMER,
        status=AccountStatus.PENDING,
    )
    registration, document = _submitted_registration(
        user,
        region,
        license_type="WHOLESALER_LICENSE",
    )
    api.force_authenticate(user=user_admin)
    response = api.post(
        f"/api/v1/admin/registration-documents/{document.pk}/verification/",
        {"verified": True},
        format="json",
    )
    assert response.status_code == 200, response.data

    response = api.post(
        f"/api/v1/admin/registrations/{registration.pk}/decision/",
        {"action": "APPROVE"},
        format="json",
    )
    assert response.status_code == 400
    assert "required business license" in str(response.data).lower()
    user.refresh_from_db()
    assert user.status == AccountStatus.PENDING


def test_super_admin_can_verify_then_approve_and_duplicate_is_conflict(api, super_admin):
    region = _location("Nationwide Review Region", "nationwide-review-region")
    user = User.objects.create_user(
        email="superadmin-review@test.et",
        password="Str0ngPass!23",
        full_name="Super Admin Review Farmer",
        phone="+251911000005",
        role=Role.FARMER,
        status=AccountStatus.PENDING,
    )
    registration, document = _submitted_registration(user, region)
    api.force_authenticate(user=super_admin)

    review_list = api.get("/api/v1/admin/registrations/")
    assert review_list.status_code == 200
    assert str(registration.pk) in {row["id"] for row in review_list.data["results"]}
    response = api.post(
        f"/api/v1/admin/registration-documents/{document.pk}/verification/",
        {"verified": True},
        format="json",
    )
    assert response.status_code == 200, response.data
    response = api.post(
        f"/api/v1/superadmin/users/{user.pk}/override/",
        {"decision": "APPROVE"},
        format="json",
    )
    assert response.status_code == 200, response.data
    response = api.post(
        f"/api/v1/superadmin/users/{user.pk}/override/",
        {"decision": "APPROVE"},
        format="json",
    )
    assert response.status_code == 409, response.data
    assert RegistrationReview.objects.filter(
        registration=registration,
        action=RegistrationReview.Action.APPROVED,
    ).count() == 1


def test_top_level_user_admin_can_create_only_scoped_subordinate_staff(api, user_admin):
    region = _location("Staff Region", "staff-region")
    zone = _location(
        "Staff Zone",
        "staff-zone",
        parent=region,
        level=LocationLevel.ZONE,
    )
    api.force_authenticate(user=user_admin)
    response = api.post(
        "/api/v1/superadmin/accounts/",
        {
            "full_name": "Delegated Zonal Admin",
            "email": "delegated-zone@test.et",
            "password": "Str0ngPass!23",
            "role": Role.USER_ADMIN,
            "scope_level": "LOCATION",
            "scope_type": "ZONAL",
            "scope_location": str(zone.pk),
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    created = User.objects.get(email="delegated-zone@test.et")
    scope = AdministratorScope.objects.get(user=created)
    assert scope.location == zone

    response = api.post(
        "/api/v1/superadmin/accounts/",
        {
            "full_name": "Unauthorized National Admin",
            "email": "delegated-national@test.et",
            "password": "Str0ngPass!23",
            "role": Role.USER_ADMIN,
            "scope_level": "GLOBAL",
            "scope_type": "TOP_LEVEL",
        },
        format="json",
    )
    assert response.status_code == 400
    assert not User.objects.filter(email="delegated-national@test.et").exists()


def test_regional_admin_cannot_create_staff_outside_assigned_region(api):
    north = _location("North Staff Region", "north-staff-region")
    north_zone = _location(
        "North Staff Zone",
        "north-staff-zone",
        parent=north,
        level=LocationLevel.ZONE,
    )
    south = _location("South Staff Region", "south-staff-region")
    south_zone = _location(
        "South Staff Zone",
        "south-staff-zone",
        parent=south,
        level=LocationLevel.ZONE,
    )
    regional_admin = User.objects.create_user(
        email="regional-staff-admin@test.et",
        password="Str0ngPass!23",
        full_name="Regional Staff Admin",
        role=Role.USER_ADMIN,
        status=AccountStatus.APPROVED,
    )
    scope = AdministratorScope.objects.get(user=regional_admin)
    scope.level = AdministratorScope.Level.LOCATION
    scope.location = north
    scope.save()
    assert not can_assign_admin_scope(
        regional_admin,
        AdministratorScope.Level.LOCATION,
        south_zone,
        "ZONAL",
    )
    api.force_authenticate(user=regional_admin)

    inside = api.post(
        "/api/v1/superadmin/accounts/",
        {
            "full_name": "North Zone Admin",
            "email": "north-zone-admin@test.et",
            "password": "Str0ngPass!23",
            "role": Role.USER_ADMIN,
            "scope_level": "LOCATION",
            "scope_type": "ZONAL",
            "scope_location": str(north_zone.pk),
        },
        format="json",
    )
    assert inside.status_code == 201, inside.data

    outside = api.post(
        "/api/v1/superadmin/accounts/",
        {
            "full_name": "South Zone Admin",
            "email": "south-zone-admin@test.et",
            "password": "Str0ngPass!23",
            "role": Role.USER_ADMIN,
            "scope_level": "LOCATION",
            "scope_type": "ZONAL",
            "scope_location": str(south_zone.pk),
        },
        format="json",
    )
    assert outside.status_code == 400
    assert not User.objects.filter(email="south-zone-admin@test.et").exists()


def test_super_admin_can_create_multiple_scoped_admins_for_the_same_location(
    api, super_admin
):
    region = _location("Admin Region", "admin-create-region")
    api.force_authenticate(user=super_admin)

    for suffix in ("one", "two"):
        response = api.post(
            "/api/v1/superadmin/accounts/",
            {
                "full_name": f"Scoped Admin {suffix}",
                "email": f"scoped-admin-{suffix}@test.et",
                "password": "Str0ngPass!23",
                "role": Role.USER_ADMIN,
                "scope_level": "LOCATION",
                "scope_location": str(region.pk),
            },
            format="json",
        )
        assert response.status_code == 201, response.data

    scopes = AdministratorScope.objects.filter(location=region).select_related("user")
    assert scopes.count() == 2
    response = api.get("/api/v1/superadmin/admin-scopes/")
    assert response.status_code == 200, response.data
    expected_emails = {"scoped-admin-one@test.et", "scoped-admin-two@test.et"}
    payloads = [
        item
        for item in response.data["results"]
        if item["user_email"] in expected_emails
    ]
    assert len(payloads) == 2, response.data
    assert {item["location_name"] for item in payloads} == {region.name}
    assert all(item["location_path"] == [region.name] for item in payloads)
    assert {item["scope_label"] for item in payloads} == {"Regional Admin"}


def test_super_admin_cannot_create_unscoped_user_admin(api, super_admin):
    api.force_authenticate(user=super_admin)
    response = api.post(
        "/api/v1/superadmin/accounts/",
        {
            "full_name": "Unscoped Admin",
            "email": "unscoped-admin@test.et",
            "password": "Str0ngPass!23",
            "role": Role.USER_ADMIN,
        },
        format="json",
    )
    assert response.status_code == 400
    assert not User.objects.filter(email="unscoped-admin@test.et").exists()


def test_staff_list_supports_scope_role_and_geographic_filters(api, super_admin):
    region = _location("Filtered Region", "staff-filter-region")
    zone = _location(
        "Filtered Zone",
        "staff-filter-zone",
        parent=region,
        level=LocationLevel.ZONE,
    )
    other_region = _location("Other Region", "staff-filter-other-region")
    in_scope = User.objects.create_user(
        email="filter-zonal@test.et",
        password="TestPass123!",
        full_name="Filtered Zonal Admin",
        role=Role.USER_ADMIN,
        status=AccountStatus.APPROVED,
    )
    AdministratorScope.objects.filter(user=in_scope).update(
        level=AdministratorScope.Level.LOCATION,
        location=zone,
    )
    out_of_scope = User.objects.create_user(
        email="filter-other@test.et",
        password="TestPass123!",
        full_name="Other Regional Admin",
        role=Role.USER_ADMIN,
        status=AccountStatus.APPROVED,
    )
    AdministratorScope.objects.filter(user=out_of_scope).update(
        level=AdministratorScope.Level.LOCATION,
        location=other_region,
    )
    api.force_authenticate(user=super_admin)

    response = api.get(
        "/api/v1/superadmin/accounts/",
        {
            "role": Role.USER_ADMIN,
            "scope_type": "ZONAL",
            "location_id": str(region.pk),
        },
    )

    assert response.status_code == 200, response.data
    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == str(in_scope.pk)


def test_staff_activity_reports_audited_actions_separately_from_scope_totals(
    api,
    super_admin,
):
    region = _location("Staff Activity Region", "staff-activity-region")
    staff = User.objects.create_user(
        email="activity-regional@test.et",
        password="TestPass123!",
        full_name="Activity Regional Admin",
        role=Role.USER_ADMIN,
        status=AccountStatus.APPROVED,
    )
    AdministratorScope.objects.filter(user=staff).update(
        level=AdministratorScope.Level.LOCATION,
        location=region,
    )
    AuditLog.objects.create(
        actor=super_admin,
        action="admin_account_created",
        target=staff.email,
    )
    AuditLog.objects.create(
        actor=staff,
        action="user_approved",
        target="approved-in-region@test.et",
    )
    AuditLog.objects.create(
        actor=staff,
        action="user_rejected",
        target="rejected-in-region@test.et",
    )
    for email, status in (
        ("regional-pending-one@test.et", RegistrationStatus.SUBMITTED),
        ("regional-pending-two@test.et", RegistrationStatus.DRAFT),
    ):
        user = User.objects.create_user(
            email=email,
            password="TestPass123!",
            full_name=email.split("@")[0],
            role=Role.FARMER,
            status=AccountStatus.PENDING,
        )
        UserRegistration.objects.create(user=user, location=region, status=status)

    api.force_authenticate(user=super_admin)
    response = api.get(
        f"/api/v1/superadmin/accounts/{staff.pk}/activity/",
        {"days": "7"},
    )

    assert response.status_code == 200, response.data
    assert response.data["staff"]["created_by"]["id"] == str(super_admin.pk)
    assert response.data["statistics"]["actions"] == 2
    assert response.data["statistics"]["approved"] == 1
    assert response.data["statistics"]["rejected"] == 1
    assert response.data["statistics"]["current_scope_farmers"] == 2
    assert response.data["statistics"]["pending_approvals_in_scope"] == 2
    assert response.data["count"] == 2


def test_regional_admin_cannot_open_activity_for_staff_outside_its_scope(api):
    assigned_region = _location("Activity Assigned Region", "activity-assigned-region")
    other_region = _location("Activity Other Region", "activity-other-region")
    zone = _location(
        "Activity Other Zone",
        "activity-other-zone",
        parent=other_region,
        level=LocationLevel.ZONE,
    )
    regional_admin = User.objects.create_user(
        email="activity-scope-admin@test.et",
        password="TestPass123!",
        full_name="Activity Scope Admin",
        role=Role.USER_ADMIN,
        status=AccountStatus.APPROVED,
    )
    AdministratorScope.objects.filter(user=regional_admin).update(
        level=AdministratorScope.Level.LOCATION,
        location=assigned_region,
    )
    out_of_scope_staff = User.objects.create_user(
        email="activity-outside-zone@test.et",
        password="TestPass123!",
        full_name="Outside Zonal Admin",
        role=Role.USER_ADMIN,
        status=AccountStatus.APPROVED,
    )
    AdministratorScope.objects.filter(user=out_of_scope_staff).update(
        level=AdministratorScope.Level.LOCATION,
        location=zone,
    )
    api.force_authenticate(user=regional_admin)

    response = api.get(
        f"/api/v1/superadmin/accounts/{out_of_scope_staff.pk}/activity/"
    )

    assert response.status_code == 404
