"""Real-time fan-out helpers (doc 4.4 / 4.11.2).

Django Channels' channel layer is the single transport for both chat and
notification delivery.  Views and signal receivers run in synchronous worker
threads, so ``group_send`` is dispatched with ``async_to_sync`` — this works
with the in-memory layer in development and Redis in production without any
code change.
"""
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

CHAT_GROUP_PREFIX = "chat"
NOTIFICATION_GROUP_PREFIX = "notify"


def chat_group(channel_id) -> str:
    return f"{CHAT_GROUP_PREFIX}_{channel_id}"


def notification_group(user_id) -> str:
    return f"{NOTIFICATION_GROUP_PREFIX}_{user_id}"


def push_to_group(group: str, payload: dict) -> bool:
    """Best-effort ``group_send`` from synchronous code.

    Real-time delivery is an enhancement over the persisted records, so a
    transport failure must never fail the originating HTTP request.
    """
    try:
        layer = get_channel_layer()
        if layer is None:
            return False
        async_to_sync(layer.group_send)(group, payload)
        return True
    except Exception:  # pragma: no cover - transport level failure
        logger.warning("Could not push to channel group %s", group, exc_info=True)
        return False


def push_chat_event(channel_id, payload: dict) -> bool:
    payload = dict(payload)
    payload.setdefault("type", "chat.event")
    return push_to_group(chat_group(channel_id), payload)


def push_notification_event(user_id, payload: dict) -> bool:
    payload = dict(payload)
    payload.setdefault("type", "notify.event")
    return push_to_group(notification_group(user_id), payload)
