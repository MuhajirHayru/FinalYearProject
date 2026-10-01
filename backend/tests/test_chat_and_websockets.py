"""Chat, WebSocket and notification tests (UC-03, doc 5.1.4, FR-F-08, FR-W-06)."""
import json

import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import RefreshToken

from chat.models import ChatChannel, Message
from greenpath.asgi import application
from notifications.models import Notification
from notifications.services import notify
from users.models import AccountStatus, User

pytestmark = pytest.mark.django_db(transaction=True)


def token_for(user):
    return str(RefreshToken.for_user(user).access_token)


@pytest.fixture
def outsider(db):
    return User.objects.create_user(
        email="chat-outsider@test.et", password="demo1234", full_name="Chat Outsider",
        role="RETAILER", status=AccountStatus.APPROVED,
    )


@pytest.fixture
def outsider_token(outsider):
    return token_for(outsider)


# ---------------------------------------------------------------------------
# REST: channels
# ---------------------------------------------------------------------------
def test_channel_list_only_includes_members(api, chat_channel, farmer, outsider):
    api.force_authenticate(user=farmer)
    response = api.get("/api/v1/chat/channels/")
    assert response.status_code == 200
    assert str(chat_channel.id) in [str(row["id"]) for row in response.data["results"]]

    api.force_authenticate(user=outsider)
    response = api.get("/api/v1/chat/channels/")
    assert str(chat_channel.id) not in [str(r["id"]) for r in response.data["results"]]


def test_farmer_opens_channel_with_wholesaler(api, farmer, wholesaler):
    api.force_authenticate(user=farmer)
    response = api.post(
        "/api/v1/chat/channels/",
        {"participant_ids": [str(wholesaler.id)]},
        format="json",
    )
    assert response.status_code == 201, response.data
    channel = ChatChannel.objects.latest("created_at")
    assert set(channel.participants.values_list("pk", flat=True)) == {
        farmer.pk, wholesaler.pk
    }


def test_farmer_cannot_contact_another_farmer(api, farmer, farmer_b):
    api.force_authenticate(user=farmer)
    response = api.post(
        "/api/v1/chat/channels/",
        {"participant_ids": [str(farmer_b.id)]},
        format="json",
    )
    assert response.status_code == 403


def test_farmer_cannot_contact_retailer_directly(api, farmer, retailer):
    api.force_authenticate(user=farmer)
    response = api.post(
        "/api/v1/chat/channels/",
        {"participant_ids": [str(retailer.id)]},
        format="json",
    )
    assert response.status_code == 403


def test_channel_create_requires_a_participant(api, farmer):
    api.force_authenticate(user=farmer)
    response = api.post("/api/v1/chat/channels/", {}, format="json")
    assert response.status_code == 400


def test_reopening_a_channel_reuses_the_existing_one(api, farmer, wholesaler):
    api.force_authenticate(user=farmer)
    payload = {"participant_ids": [str(wholesaler.id)]}
    first = api.post("/api/v1/chat/channels/", payload, format="json")
    second = api.post("/api/v1/chat/channels/", payload, format="json")
    assert first.status_code == 201 and second.status_code == 201
    assert ChatChannel.objects.count() == 1


# ---------------------------------------------------------------------------
# REST: messages
# ---------------------------------------------------------------------------
def test_message_history_requires_participation(api, chat_channel, farmer, outsider):
    Message.objects.create(channel=chat_channel, sender=farmer, content="Hello")
    url = f"/api/v1/chat/channels/{chat_channel.id}/messages/"

    api.force_authenticate(user=farmer)
    assert api.get(url).status_code == 200

    api.force_authenticate(user=outsider)
    assert api.get(url).status_code == 404


def test_non_member_cannot_post_into_a_channel(api, chat_channel, outsider):
    url = f"/api/v1/chat/channels/{chat_channel.id}/messages/"
    api.force_authenticate(user=outsider)
    response = api.post(url, {"content": "let me in"}, format="json")
    assert response.status_code == 404
    assert Message.objects.filter(channel=chat_channel).count() == 0


def test_member_can_send_a_message(api, chat_channel, farmer, wholesaler):
    api.force_authenticate(user=farmer)
    response = api.post(
        f"/api/v1/chat/channels/{chat_channel.id}/messages/",
        {"content": "Is 500 kg of tomato available?"},
        format="json",
    )
    assert response.status_code == 201, response.data
    message = Message.objects.get(channel=chat_channel)
    assert message.sender_id == farmer.id
    chat_channel.refresh_from_db()
    assert chat_channel.last_message_at == message.sent_at
    # message_received domain event notifies the other participant
    assert Notification.objects.filter(recipient=wholesaler, type="MESSAGE").exists()


def test_empty_message_rejected(api, chat_channel, farmer):
    api.force_authenticate(user=farmer)
    response = api.post(
        f"/api/v1/chat/channels/{chat_channel.id}/messages/",
        {"content": "   "},
        format="json",
    )
    assert response.status_code == 400


def test_mark_read_clears_unread(api, chat_channel, wholesaler, farmer):
    Message.objects.create(channel=chat_channel, sender=farmer, content="Hello")
    assert chat_channel.get_unread_count(wholesaler) == 1

    api.force_authenticate(user=wholesaler)
    response = api.post(f"/api/v1/chat/channels/{chat_channel.id}/mark-read/")
    assert response.status_code == 200, response.data
    assert response.data["updated"] == 1
    assert chat_channel.get_unread_count(wholesaler) == 0


def test_unread_count_reported_on_channel_detail(api, chat_channel, wholesaler, farmer):
    Message.objects.create(channel=chat_channel, sender=farmer, content="One")
    api.force_authenticate(user=wholesaler)
    response = api.get(f"/api/v1/chat/channels/{chat_channel.id}/")
    assert response.status_code == 200
    assert response.data["unread_count"] == 1
    assert response.data["last_message"]["content"] == "One"


# ---------------------------------------------------------------------------
# WebSocket consumers
# ---------------------------------------------------------------------------
async def ws_connect(path):
    """Connect and return ``(connected, close_code)``.

    The consumer closes unauthenticated or unauthorised handshakes with 4401
    (see ``chat/consumers.py``); asserting the code proves the *consumer*
    rejected the connection rather than the origin validator.
    """
    communicator = WebsocketCommunicator(application, path)
    connected, code = await communicator.connect()
    return communicator, connected, code


async def test_chat_websocket_rejects_missing_token(chat_channel):
    _, connected, code = await ws_connect(f"/ws/chat/{chat_channel.id}/")
    assert connected is False
    assert code == 4401


async def test_chat_websocket_rejects_invalid_token(chat_channel):
    _, connected, code = await ws_connect(
        f"/ws/chat/{chat_channel.id}/?token=not-a-jwt"
    )
    assert connected is False
    assert code == 4401


async def test_chat_websocket_rejects_non_participant(chat_channel, outsider_token):
    _, connected, code = await ws_connect(
        f"/ws/chat/{chat_channel.id}/?token={outsider_token}"
    )
    assert connected is False
    assert code == 4403


async def test_chat_websocket_persists_and_fans_out(chat_channel, farmer):
    communicator, connected, _ = await ws_connect(
        f"/ws/chat/{chat_channel.id}/?token={token_for(farmer)}"
    )
    assert connected is True

    await communicator.send_to(
        json.dumps({"type": "chat.message", "content": "Do you deliver to Bahir Dar?"})
    )
    payload = await communicator.receive_json_from()
    assert payload["type"] == "chat.message"
    assert payload["message"]["content"] == "Do you deliver to Bahir Dar?"
    assert payload["message"]["sender_name"] == farmer.full_name
    await communicator.disconnect()

    assert await sync_to_async(Message.objects.filter(channel=chat_channel).count)() == 1
    assert await sync_to_async(
        Message.objects.filter(content="Do you deliver to Bahir Dar?").exists
    )()


async def test_chat_websocket_typing_broadcast(chat_channel, farmer):
    communicator, connected, _ = await ws_connect(
        f"/ws/chat/{chat_channel.id}/?token={token_for(farmer)}"
    )
    assert connected is True
    await communicator.send_to(json.dumps({"type": "chat.typing", "is_typing": True}))
    payload = await communicator.receive_json_from()
    assert payload["type"] == "chat.typing"
    assert payload["is_typing"] is True
    await communicator.disconnect()


async def test_chat_websocket_rejects_pending_user(chat_channel, pending_user):
    _, connected, code = await ws_connect(
        f"/ws/chat/{chat_channel.id}/?token={token_for(pending_user)}"
    )
    assert connected is False
    assert code == 4401


async def test_chat_websocket_rejects_suspended_user(chat_channel, farmer):
    token = token_for(farmer)
    await sync_to_async(setattr)(farmer, "status", AccountStatus.SUSPENDED)
    await sync_to_async(farmer.save)(update_fields=["status"])
    _, connected, code = await ws_connect(f"/ws/chat/{chat_channel.id}/?token={token}")
    assert connected is False
    assert code == 4401


async def test_notification_websocket_rejects_anonymous():
    _, connected, code = await ws_connect("/ws/notifications/")
    assert connected is False
    assert code == 4401


async def test_notification_websocket_receives_persisted_notification(farmer):
    await sync_to_async(Notification.objects.create)(
        recipient=farmer, type="SYSTEM", message="Queued before connecting"
    )
    communicator, connected, _ = await ws_connect(
        f"/ws/notifications/?token={token_for(farmer)}"
    )
    assert connected is True

    # The first frame is the readiness handshake carrying the unread count.
    ready = await communicator.receive_json_from()
    assert ready["type"] == "notify.ready"
    assert ready["unread_count"] == 1

    # A notification raised after the handshake is pushed over the socket.
    await sync_to_async(notify)(
        user_ids=[farmer.id], type="SYSTEM", message="Pong", actor=None
    )
    payload = await communicator.receive_json_from()
    assert payload["type"] == "notify.event"
    assert payload["notification"]["message"] == "Pong"

    await communicator.send_to(json.dumps({"type": "notify.mark_all_read"}))
    read = await communicator.receive_json_from()
    assert read["type"] == "notify.read"
    assert read["unread_count"] == 0
    await communicator.disconnect()
    assert await sync_to_async(
        Notification.objects.filter(recipient=farmer, is_read=False).count
    )() == 0
