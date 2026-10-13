import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from users.models import AuditLog, WebsiteContent

pytestmark = pytest.mark.django_db


def test_public_website_content_has_safe_defaults(api):
    response = api.get("/api/v1/auth/website-content/")

    assert response.status_code == 200
    assert response.data["platform_name"] == "Green Path"
    assert response.data["content"]["landing_title"]
    assert response.data["logo_url"] is None


def test_only_super_admin_can_update_website_content(api, user_admin):
    api.force_authenticate(user=user_admin)

    response = api.patch(
        "/api/v1/superadmin/website-content/",
        {"platform_name": "Restricted"},
        format="json",
    )

    assert response.status_code == 403
    assert not WebsiteContent.objects.exists()


def test_super_admin_updates_persistent_content_and_audits_change(api, super_admin):
    api.force_authenticate(user=super_admin)

    response = api.patch(
        "/api/v1/superadmin/website-content/",
        {
            "platform_name": "Green Path Systems",
            "content": {
                "landing_title": "A new public title",
                "contact_email": "support@example.et",
            },
        },
        format="json",
    )

    assert response.status_code == 200, response.data
    website = WebsiteContent.objects.get(pk=WebsiteContent.SINGLETON_PK)
    assert website.platform_name == "Green Path Systems"
    assert website.content["landing_title"] == "A new public title"
    assert website.content["contact_email"] == "support@example.et"
    assert AuditLog.objects.filter(
        actor=super_admin, action="website_content_updated"
    ).exists()

    public = APIClient().get("/api/v1/auth/website-content/")
    assert public.data["platform_name"] == "Green Path Systems"
    assert public.data["content"]["landing_title"] == "A new public title"


def test_website_content_rejects_unknown_copy_keys_and_invalid_images(api, super_admin):
    api.force_authenticate(user=super_admin)
    invalid = api.patch(
        "/api/v1/superadmin/website-content/",
        {"content": {"role_id": "SUPER_ADMIN"}},
        format="json",
    )
    invalid_image = api.patch(
        "/api/v1/superadmin/website-content/",
        {
            "logo": SimpleUploadedFile(
                "not-a-logo.png", b"not an image", content_type="image/png"
            )
        },
        format="multipart",
    )

    assert invalid.status_code == 400
    assert invalid_image.status_code == 400
