from django.urls import path

from .views import AssistantConversationDetailView, AssistantConversationListView
from .views import AssistantMessageListView, AssistantTranscriptionView

urlpatterns = [
    path(
        "conversations/",
        AssistantConversationListView.as_view(),
        name="assistant-conversations",
    ),
    path(
        "conversations/<uuid:conversation_id>/",
        AssistantConversationDetailView.as_view(),
        name="assistant-conversation-detail",
    ),
    path(
        "conversations/<uuid:conversation_id>/messages/",
        AssistantMessageListView.as_view(),
        name="assistant-messages",
    ),
    path(
        "transcribe/",
        AssistantTranscriptionView.as_view(),
        name="assistant-transcribe",
    ),
]
