"""Live-presence connection and heartbeat coverage."""

import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import RefreshToken

from greenpath.asgi import application
from users.models import User

pytestmark = pytest.mark.django_db(transaction=True)


def token_for(user):
    return str(RefreshToken.for_user(user).access_token)


async def test_presence_tracks_multiple_connections_and_heartbeats(farmer):
    path = f"/ws/presence/?token={token_for(farmer)}"
    first = WebsocketCommunicator(application, path)
    second = WebsocketCommunicator(application, path)

    connected, code = await first.connect()
    assert connected, code
    connected, code = await second.connect()
    assert connected, code
    assert await sync_to_async(
        lambda: User.objects.get(pk=farmer.pk).is_online
    )()

    await first.send_json_to({"action": "heartbeat"})
    messages = []
    for _ in range(3):
        try:
            messages.append(await first.receive_json_from(timeout=0.2))
        except TimeoutError:
            break
        if messages[-1].get("type") == "presence.heartbeat":
            break
    assert any(message.get("type") == "presence.heartbeat" for message in messages)

    await first.disconnect()
    assert await sync_to_async(
        lambda: User.objects.get(pk=farmer.pk).is_online
    )()

    await second.disconnect()
    assert not await sync_to_async(
        lambda: User.objects.get(pk=farmer.pk).is_online
    )()


async def test_retailer_can_observe_presence_without_becoming_online(retailer):
    communicator = WebsocketCommunicator(
        application, f"/ws/presence/?token={token_for(retailer)}"
    )
    connected, code = await communicator.connect()
    assert connected, code
    assert not await sync_to_async(
        lambda: User.objects.get(pk=retailer.pk).is_online
    )()
    await communicator.disconnect()
