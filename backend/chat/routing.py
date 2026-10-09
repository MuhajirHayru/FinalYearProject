from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(
        r"ws/chat/(?P<channel_id>[0-9a-fA-F-]+)/$",
        consumers.ChatConsumer.as_asgi(),
    ),
    re_path(
        r"ws/notifications/$",
        consumers.NotificationConsumer.as_asgi(),
    ),
    re_path(
        r"ws/presence/$",
        consumers.PresenceConsumer.as_asgi(),
    ),
]
