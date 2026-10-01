from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import ChannelMessagesViewSet, ChatChannelViewSet, MarkChannelReadView

router = DefaultRouter()
router.register("channels", ChatChannelViewSet, basename="chat-channels")
router.register(
    r"channels/(?P<channel_pk>[0-9a-fA-F-]+)/messages",
    ChannelMessagesViewSet,
    basename="channel-messages",
)

urlpatterns = router.urls + [
    path(
        "channels/<uuid:channel_pk>/mark-read/",
        MarkChannelReadView.as_view({"post": "create"}),
        name="channel-mark-read",
    ),
]
