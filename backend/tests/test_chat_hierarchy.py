import json

import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import RefreshToken

from chat.models import ChatChannel
from greenpath.asgi import application
from registrations.models import (
    AdministratorScope,
    AdministrativeLocation,
    LocationLevel,
)
from users.models import Role, User

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def scoped_admins():
    region = AdministrativeLocation.objects.create(
        source_id="chat-region-a",
        name="Chat Region A",
        level=LocationLevel.REGION,
    )
    zone = AdministrativeLocation.objects.create(
        source_id="chat-zone-a",
        name="Chat Zone A",
        level=LocationLevel.ZONE,
        parent=region,
    )
    other_region = AdministrativeLocation.objects.create(
        source_id="chat-region-b",
        name="Chat Region B",
        level=LocationLevel.REGION,
    )

    def create_admin(email, name, location):
        user = User.objects.create_user(
            email=email,
            password="test-password",
            full_name=name,
            role=Role.USER_ADMIN,
        )
        scope, _ = AdministratorScope.objects.get_or_create(
            user=user,
            defaults={
                "level": AdministratorScope.Level.LOCATION,
                "location": location,
            },
        )
        if scope.location_id != location.pk or scope.level != AdministratorScope.Level.LOCATION:
            scope.level = AdministratorScope.Level.LOCATION
            scope.location = location
            scope.save(update_fields=["level", "location"])
        return user

    return (
        create_admin("region-admin@test.et", "Region Admin", region),
        create_admin("zone-admin@test.et", "Zone Admin", zone),
        create_admin("other-region-admin@test.et", "Other Region Admin", other_region),
    )


def test_admin_can_start_conversation_with_descendant_admin(api, scoped_admins):
    regional_admin, zonal_admin, _ = scoped_admins
    api.force_authenticate(user=regional_admin)

    response = api.post(
        "/api/v1/chat/channels/",
        {"participant_ids": [str(zonal_admin.pk)]},
        format="json",
    )

    assert response.status_code == 201, response.data
    channel = ChatChannel.objects.get()
    assert set(channel.participants.values_list("pk", flat=True)) == {
        regional_admin.pk,
        zonal_admin.pk,
    }


def test_admin_cannot_start_or_discover_conversation_outside_scope(
    api, scoped_admins
):
    regional_admin, _, unrelated_admin = scoped_admins
    api.force_authenticate(user=regional_admin)

    attempted = api.post(
        "/api/v1/chat/channels/",
        {"participant_ids": [str(unrelated_admin.pk)]},
        format="json",
    )
    assert attempted.status_code == 403

    channel = ChatChannel.objects.create()
    channel.participants.add(regional_admin, unrelated_admin)
    assert api.get("/api/v1/chat/channels/").data["count"] == 0
    assert api.get(f"/api/v1/chat/channels/{channel.pk}/").status_code == 404
    assert (
        api.get(f"/api/v1/chat/channels/{channel.pk}/messages/").status_code
        == 404
    )
    assert (
        api.post(f"/api/v1/chat/channels/{channel.pk}/mark-read/").status_code
        == 404
    )


async def test_admin_websocket_rejects_conversation_outside_scope(scoped_admins):
    regional_admin, _, unrelated_admin = scoped_admins
    channel = await sync_to_async(ChatChannel.objects.create)()
    await sync_to_async(channel.participants.add)(regional_admin, unrelated_admin)
    token = str(RefreshToken.for_user(regional_admin).access_token)

    communicator = WebsocketCommunicator(
        application, f"/ws/chat/{channel.pk}/?token={token}"
    )
    connected, code = await communicator.connect()

    assert connected is False
    assert code == 4403


def test_top_level_admin_can_message_scoped_admin(api, scoped_admins, super_admin):
    regional_admin, _, _ = scoped_admins
    AdministratorScope.objects.create(
        user=super_admin,
        level=AdministratorScope.Level.GLOBAL,
    )
    api.force_authenticate(user=super_admin)

    response = api.post(
        "/api/v1/chat/channels/",
        {"participant_ids": [str(regional_admin.pk)]},
        format="json",
    )

    assert response.status_code == 201, response.data
