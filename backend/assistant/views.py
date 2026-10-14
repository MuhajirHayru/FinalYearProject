from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from .models import AssistantConversation, AssistantMessage
from .provider import AssistantProviderError, get_assistant_reply, transcribe_audio
from .serializers import (
    AssistantConversationSerializer,
    AssistantMessageSerializer,
    AssistantSendMessageSerializer,
)


class AssistantConversationPagination(PageNumberPagination):
    page_size = 30
    max_page_size = 30


class AssistantConversationListView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "assistant_chat"
    serializer_class = AssistantConversationSerializer
    pagination_class = AssistantConversationPagination

    def get_queryset(self):
        return AssistantConversation.objects.filter(owner=self.request.user)[:30]

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AssistantConversationDetailView(generics.DestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "assistant_chat"
    serializer_class = AssistantConversationSerializer
    lookup_url_kwarg = "conversation_id"

    def get_queryset(self):
        return AssistantConversation.objects.filter(owner=self.request.user)


class AssistantMessagePagination(PageNumberPagination):
    page_size = 100
    max_page_size = 100


class AssistantMessageListView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "assistant_chat"
    serializer_class = AssistantMessageSerializer
    pagination_class = AssistantMessagePagination
    lookup_url_kwarg = "conversation_id"

    def get_conversation(self):
        return get_object_or_404(
            AssistantConversation,
            owner=self.request.user,
            pk=self.kwargs["conversation_id"],
        )

    def get_queryset(self):
        return self.get_conversation().messages.all()[:100]

    def create(self, request, *args, **kwargs):
        conversation = self.get_conversation()
        serializer = AssistantSendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        content = serializer.validated_data["content"]
        language = serializer.validated_data.get("language", conversation.language)
        history = list(
            conversation.messages.order_by("-created_at")
            .values("role", "content")[:12]
        )
        history.reverse()
        history.append({"role": AssistantMessage.Role.USER, "content": content})
        try:
            reply = get_assistant_reply(request.user, language, history)
        except AssistantProviderError as error:
            return Response(
                {"error": str(error)}, status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        with transaction.atomic():
            conversation = get_object_or_404(
                AssistantConversation.objects.select_for_update(),
                owner=request.user,
                pk=conversation.pk,
            )
            if serializer.validated_data.get("language"):
                conversation.language = language
            if not conversation.messages.exists():
                conversation.title = content[:77] + ("..." if len(content) > 80 else "")
            conversation.save(update_fields=["language", "title", "updated_at"])
            user_message = AssistantMessage.objects.create(
                conversation=conversation,
                role=AssistantMessage.Role.USER,
                content=content,
            )
            assistant_message = AssistantMessage.objects.create(
                conversation=conversation,
                role=AssistantMessage.Role.ASSISTANT,
                content=reply,
            )
        return Response(
            {
                "user_message": AssistantMessageSerializer(user_message).data,
                "assistant_message": AssistantMessageSerializer(assistant_message).data,
            },
            status=status.HTTP_201_CREATED,
        )


class AssistantTranscriptionView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "assistant_transcription"
    parser_classes = [MultiPartParser]

    def post(self, request, *args, **kwargs):
        audio = request.FILES.get("audio")
        if audio is None:
            raise ValidationError({"audio": "Upload a voice recording."})
        if audio.size <= 0:
            raise ValidationError({"audio": "The recording is empty."})
        if audio.size > settings.GROQ_MAX_AUDIO_BYTES:
            raise ValidationError({"audio": "Recordings must be 10 MB or smaller."})
        content_type = (audio.content_type or "").split(";", 1)[0].lower()
        if content_type not in {
            "audio/flac",
            "audio/m4a",
            "audio/mp3",
            "audio/mp4",
            "audio/mpeg",
            "audio/mpga",
            "audio/wav",
            "audio/webm",
            "audio/x-wav",
        }:
            raise ValidationError({"audio": "Upload a supported audio recording."})
        language = request.data.get("language", "auto")
        if language not in ("auto", "en", "am", "om"):
            raise ValidationError({"language": "Choose auto, en, am, or om."})
        try:
            text = transcribe_audio(audio.read(), audio.name, language)
        except AssistantProviderError as error:
            return Response(
                {"error": str(error)}, status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        return Response({"text": text})
