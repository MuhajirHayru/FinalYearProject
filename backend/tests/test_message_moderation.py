import json

import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import AccessToken

from chat.models import Message
from greenpath.asgi import application
from users.models import PlatformSettings

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.parametrize(
    "content",
    [
        "Call me at 0911 234 567",
        "My number is +251-911-234-567",
        "Write to seller@example.com",
        "My email is seller at example dot com",
        "Meet at 9.123456, 38.123456",
        "My Kebele 04 house is ready",
        "Message me on WhatsApp",
        "Contact me outside the platform",
        "Reach me at @farm_owner",
        "See https://example.com",
    ],
)
def test_rest_message_rejects_private_contact_or_precise_location(
    api, chat_channel, farmer, content
):
    api.force_authenticate(user=farmer)

    response = api.post(
        f"/api/v1/chat/channels/{chat_channel.id}/messages/",
        {"content": content},
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "private contact details" in str(response.data).lower()
    assert not Message.objects.filter(channel=chat_channel).exists()


def test_rest_message_allows_normal_agricultural_discussion(
    api, chat_channel, farmer
):
    api.force_authenticate(user=farmer)

    response = api.post(
        f"/api/v1/chat/channels/{chat_channel.id}/messages/",
        {"content": "Can you supply 500 kg of tomatoes at 80 ETB/kg?"},
        format="json",
    )

    assert response.status_code == 201, response.data
    assert Message.objects.get(channel=chat_channel).content == (
        "Can you supply 500 kg of tomatoes at 80 ETB/kg?"
    )


async def test_websocket_message_rejects_phone_before_persistence(
    chat_channel, farmer
):
    token = str(AccessToken.for_user(farmer))
    communicator = WebsocketCommunicator(
        application, f"/ws/chat/{chat_channel.id}/?token={token}"
    )

    connected, _ = await communicator.connect()
    assert connected
    await communicator.send_to(
        json.dumps(
            {"type": "chat.message", "content": "Call 0911.234.567"}
        )
    )
    response = await communicator.receive_json_from()
    assert response["type"] == "chat.error"
    assert "private contact details" in response["error"].lower()
    await communicator.disconnect()

    assert not await sync_to_async(
        Message.objects.filter(channel=chat_channel).exists
    )()


async def test_websocket_text_policy_blocks_messages_without_persistence(
    chat_channel, farmer
):
    def disable_messaging():
        policy = PlatformSettings.load()
        policy.text_messaging_enabled = False
        policy.save(update_fields=["text_messaging_enabled"])

    await sync_to_async(disable_messaging)()
    token = str(AccessToken.for_user(farmer))
    communicator = WebsocketCommunicator(
        application, f"/ws/chat/{chat_channel.id}/?token={token}"
    )

    connected, _ = await communicator.connect()
    assert connected
    await communicator.send_json_to(
        {"type": "chat.message", "content": "Can you deliver tomatoes?"}
    )
    response = await communicator.receive_json_from()
    assert response["type"] == "chat.error"
    assert "temporarily unavailable" in response["error"]
    await communicator.disconnect()

    assert not await sync_to_async(
        Message.objects.filter(channel=chat_channel).exists
    )()
