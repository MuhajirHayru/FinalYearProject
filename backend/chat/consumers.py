"""WebSocket consumers for real-time communication (doc 5.1.4).

Two consumer types back the platform:

* ``ChatConsumer`` — bidirectional messaging inside a single chat channel.
* ``NotificationConsumer`` — server-to-client in-app notification delivery.

Both authenticate the upgrade handshake from the ``?token=<JWT>`` query
parameter validated by ``users.middleware.JWTAuthMiddleware``.
"""

import asyncio
import json
import time
import uuid
from datetime import timedelta

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.core.serializers.json import DjangoJSONEncoder

from greenpath.realtime import (
    chat_group,
    notification_group,
    presence_group,
    presence_user_group,
    push_presence_event,
)
from notifications.models import Notification


class SafeJsonConsumer(AsyncJsonWebsocketConsumer):
    """``AsyncJsonWebsocketConsumer`` that can serialise model values.

    ``AsyncJsonWebsocketConsumer.send_json`` uses a bare ``json.dumps``, which
    raises ``TypeError`` on the ``UUIDField``/``DecimalField``/``datetime``
    values that DRF serializers happily return.  Encoding with Django's encoder
    keeps the WebSocket payloads identical to the REST payloads.
    """

    async def send_json(self, content, close=False):
        await self.send(text_data=json.dumps(content, cls=DjangoJSONEncoder))


class _AuthenticatedConsumer(SafeJsonConsumer):
    """Shared handshake guard: reject unauthenticated sockets before accept."""

    async def _authenticate(self):
        user = self.scope.get("user")
        if not user or user.is_anonymous:
            await self.close(code=4401)
            return None
        return user

    async def disconnect(self, code):
        group = getattr(self, "group_name", None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)


class ChatConsumer(_AuthenticatedConsumer):
    """Real-time chat: connect to ``/ws/chat/{channelID}/?token=<JWT>``."""

    async def connect(self):
        self.user = await self._authenticate()
        if self.user is None:
            return

        self.channel_id = str(self.scope["url_route"]["kwargs"]["channel_id"])
        if not await self._is_participant(self.user, self.channel_id):
            await self.close(code=4403)
            return

        self.group_name = chat_group(self.channel_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    @database_sync_to_async
    def _is_participant(self, user, channel_id):
        from .models import ChatChannel

        return ChatChannel.objects.filter(id=channel_id, participants=user).exists()

    async def receive_json(self, content, **kwargs):
        # Accept both the `action` ("message"/"typing"/"read") and the `type`
        # ("chat.message"/"chat.typing") spelling so a client can echo back the
        # envelope it receives.
        action = content.get("action") or content.get("type") or "message"
        action = {
            "chat.message": "message",
            "chat.typing": "typing",
            "chat.read": "read",
        }.get(action, action)

        if action == "message":
            text = (content.get("content") or content.get("body") or "").strip()
            if not text:
                return
            message = await self._persist(text)
            if message is None:
                await self.close(code=4404)
                return
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "chat.event",
                    "payload": {
                        "type": "chat.message",
                        "channel_id": self.channel_id,
                        "message": message,
                    },
                },
            )

        elif action == "typing":
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "chat.event",
                    "payload": {
                        "type": "chat.typing",
                        "channel_id": self.channel_id,
                        "user": self.user.full_name,
                        "is_typing": bool(content.get("is_typing", True)),
                    },
                },
            )

        elif action == "read":
            await self._mark_read()

    @database_sync_to_async
    def _persist(self, text):
        from django.utils import timezone

        from .models import ChatChannel, Message
        from .serializers import MessageSerializer

        channel = ChatChannel.objects.filter(
            id=self.channel_id, participants=self.user
        ).first()
        if channel is None:
            return None
        message = Message.objects.create(
            channel=channel, sender=self.user, content=text
        )
        channel.last_message_at = timezone.now()
        channel.save(update_fields=["last_message_at"])
        return MessageSerializer(message).data

    @database_sync_to_async
    def _mark_read(self):
        from .models import Message

        return Message.objects.filter(
            channel_id=self.channel_id, is_read=False
        ).exclude(sender=self.user).update(is_read=True)

    async def chat_event(self, event):
        await self.send_json(event.get("payload", event))

    async def chat_message(self, event):
        await self.send_json(event.get("payload", event))


class NotificationConsumer(_AuthenticatedConsumer):
    """In-app notification stream: connect to ``/ws/notifications/?token=<JWT>``."""

    async def connect(self):
        self.user = await self._authenticate()
        if self.user is None:
            return

        self.group_name = notification_group(self.user.pk)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json(
            {
                "type": "notify.ready",
                "unread_count": await self._unread_count(),
            }
        )

    @database_sync_to_async
    def _unread_count(self):
        return Notification.objects.filter(
            recipient=self.user, is_read=False
        ).count()

    async def receive_json(self, content, **kwargs):
        # Accept both the `action` and the `type` spelling so the client can
        # echo back the same envelope it receives from the server.
        action = content.get("action") or content.get("type")
        if action in ("read", "mark_all_read", "notify.mark_all_read"):
            await self._mark_all_read()
            await self.send_json({"type": "notify.read", "unread_count": 0})

    @database_sync_to_async
    def _mark_all_read(self):
        return Notification.objects.filter(
            recipient=self.user, is_read=False
        ).update(is_read=True)

    async def notify_event(self, event):
        await self.send_json(event.get("payload", event))

    async def notify_notification(self, event):
        await self.send_json(event.get("payload", event))


class PresenceConsumer(_AuthenticatedConsumer):
    """Heartbeat lease for a single authenticated marketplace connection."""

    async def connect(self):
        self.user = await self._authenticate()
        if self.user is None:
            return

        from users.models import Role

        observed_roles = {
            Role.FARMER: (Role.WHOLESALER,),
            Role.WHOLESALER: (Role.FARMER, Role.WHOLESALER),
            Role.RETAILER: (Role.WHOLESALER,),
        }.get(self.user.role)
        if observed_roles is None:
            await self.close(code=4403)
            return

        self.presence_groups = [presence_group(role) for role in observed_roles]
        self.presence_groups.append(presence_user_group(self.user.pk))
        for group in self.presence_groups:
            await self.channel_layer.group_add(group, self.channel_name)

        self.presence_session_id = uuid.uuid4()
        self.last_heartbeat = time.monotonic()
        await self.accept()
        await self._register_presence()
        self.expiry_task = asyncio.create_task(self._watch_heartbeat())

    @database_sync_to_async
    def _register_presence(self):
        from django.conf import settings
        from django.utils import timezone

        from users.models import PresenceSession

        now = timezone.now()
        cutoff = now - timedelta(seconds=settings.PRESENCE_TIMEOUT_SECONDS)
        was_online = PresenceSession.objects.filter(
            user=self.user,
            disconnected_at__isnull=True,
            last_seen_at__gte=cutoff,
        ).exists()
        PresenceSession.objects.create(
            id=self.presence_session_id,
            user=self.user,
            last_seen_at=now,
        )
        if not was_online:
            push_presence_event(self.user.role, self.user.pk, True)

    @database_sync_to_async
    def _heartbeat(self):
        from django.utils import timezone

        from users.models import PresenceSession

        return PresenceSession.objects.filter(
            id=self.presence_session_id,
            user=self.user,
            disconnected_at__isnull=True,
        ).update(last_seen_at=timezone.now())

    @database_sync_to_async
    def _deactivate_presence(self):
        from django.conf import settings
        from django.utils import timezone

        from users.models import PresenceSession

        now = timezone.now()
        was_active = PresenceSession.objects.filter(
            id=self.presence_session_id,
            user=self.user,
            disconnected_at__isnull=True,
        ).update(disconnected_at=now)
        cutoff = now - timedelta(seconds=settings.PRESENCE_TIMEOUT_SECONDS)
        remains_online = PresenceSession.objects.filter(
            user=self.user,
            disconnected_at__isnull=True,
            last_seen_at__gte=cutoff,
        ).exists()
        if was_active and not remains_online:
            push_presence_event(self.user.role, self.user.pk, False)

    async def receive_json(self, content, **kwargs):
        action = content.get("action") or content.get("type")
        if action not in ("heartbeat", "presence.heartbeat"):
            return
        if not await self._heartbeat():
            await self.close(code=4408)
            return
        self.last_heartbeat = time.monotonic()
        await self.send_json({"type": "presence.heartbeat"})

    async def _watch_heartbeat(self):
        from django.conf import settings

        timeout = settings.PRESENCE_TIMEOUT_SECONDS
        interval = min(max(timeout / 3, 1), 15)
        loop = asyncio.get_running_loop()
        while True:
            await asyncio.sleep(interval)
            if loop.time() - self.last_heartbeat > timeout:
                await self._deactivate_presence()
                await self.close(code=4408)
                return

    async def disconnect(self, code):
        task = getattr(self, "expiry_task", None)
        if task and task is not asyncio.current_task():
            task.cancel()
        if hasattr(self, "presence_session_id"):
            await self._deactivate_presence()
        for group in getattr(self, "presence_groups", ()):
            await self.channel_layer.group_discard(group, self.channel_name)

    async def presence_event(self, event):
        await self.send_json(
            {
                "type": "presence.changed",
                "user_id": event["user_id"],
                "is_online": event["is_online"],
            }
        )
