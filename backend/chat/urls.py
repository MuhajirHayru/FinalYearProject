from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    ChannelMessagesViewSet,
    ChatChannelViewSet,
    ChatMessageAudioView,
    MarkChannelReadView,
    StaffRecipientsView,
    VoiceMessageModerationViewSet,
)

router = DefaultRouter()
router.register("channels", ChatChannelViewSet, basename="chat-channels")
router.register(
    "voice-moderation",
    VoiceMessageModerationViewSet,
    basename="voice-message-moderation",
)
router.register(
    r"channels/(?P<channel_pk>[0-9a-fA-F-]+)/messages",
    ChannelMessagesViewSet,
    basename="channel-messages",
)

urlpatterns = router.urls + [
    path("staff-recipients/", StaffRecipientsView.as_view(), name="chat-staff-recipients"),
    path(
        "channels/<uuid:channel_pk>/messages/<uuid:message_pk>/audio/",
        ChatMessageAudioView.as_view(),
        name="chat-message-audio",
    ),
    path(
        "channels/<uuid:channel_pk>/mark-read/",
        MarkChannelReadView.as_view({"post": "create"}),
        name="channel-mark-read",
    ),
]
