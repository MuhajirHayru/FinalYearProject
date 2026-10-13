from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from greenpath.realtime import push_chat_event
from products.models import Product
from users.models import PlatformSettings, Role, User
from users.permissions import CanStartConversation, IsChatParticipant

from .access import (
    can_access_channel,
    can_communicate,
    can_moderate_voice,
    eligible_staff_recipients,
    related_user_admin_ids,
)
from .models import (
    ChatChannel,
    Message,
    MessageKind,
    MessageModerationStatus,
)
from .serializers import ChatChannelSerializer, MessageSerializer
from greenpath.privacy import contains_restricted_content
from .transcription import VoiceTranscriptionError, transcribe_voice
from notifications.services import notify
from users.models import AuditLog, Role
from users.permissions import IsAuthenticatedRole

class ChatChannelViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """GET/POST /api/v1/chat/channels/ — the requester's active conversations."""

    serializer_class = ChatChannelSerializer
    queryset = ChatChannel.objects.none()  # only for schema lookup-type inference

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated(), CanStartConversation()]
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = (
            ChatChannel.objects.filter(
                pk__in=ChatChannel.objects.filter(
                    participants=self.request.user
                ).values("pk")
            ).prefetch_related("participants")
            .order_by("-last_message_at", "-created_at")
        )
        if self.request.user.role == Role.USER_ADMIN:
            permitted_ids = related_user_admin_ids(self.request.user)
            queryset = queryset.annotate(
                unauthorized_admin_count=Count(
                    "participants",
                    filter=(
                        Q(participants__role=Role.USER_ADMIN)
                        & ~Q(participants__pk__in=permitted_ids)
                    ),
                )
            ).filter(unauthorized_admin_count=0)
        return queryset

    def create(self, request, *args, **kwargs):
        participant_ids = request.data.get("participant_ids") or request.data.get(
            "participants"
        )
        if not participant_ids:
            return Response(
                {"success": False, "error": "A participant is required."},
                status=400,
            )
        if not isinstance(participant_ids, (list, tuple)) or len(participant_ids) != 1:
            return Response(
                {"success": False, "error": "Choose exactly one conversation partner."},
                status=400,
            )

        other = User.objects.filter(
            id=participant_ids[0],
            status="APPROVED",
            is_active=True,
        ).first()
        if other is None:
            return Response(
                {"success": False, "error": "Choose an active, approved conversation partner."},
                status=400,
            )
        if not can_communicate(request.user, other):
            return Response(
                {
                    "success": False,
                    "error": "Your role is not allowed to communicate with this user.",
                },
                status=403,
            )

        product = None
        product_id = request.data.get("related_product")
        if product_id:
            product = Product.objects.filter(id=product_id).first()

        is_staff_conversation = (
            request.user.role
            in (Role.USER_ADMIN, Role.FINANCIAL_MANAGER, Role.SUPER_ADMIN)
            and other.role
            in (Role.USER_ADMIN, Role.FINANCIAL_MANAGER, Role.SUPER_ADMIN)
        )
        if is_staff_conversation:
            channel = None
            candidates = (
                ChatChannel.objects.filter(
                    participants=request.user,
                    related_product__isnull=True,
                )
                .prefetch_related("participants")
                .order_by("-last_message_at", "-created_at")
            )
            expected_participants = {request.user.pk, other.pk}
            for candidate in candidates:
                if {
                    participant.pk
                    for participant in candidate.participants.all()
                } == expected_participants:
                    channel = candidate
                    break
        else:
            channel = (
                ChatChannel.objects.filter(participants=request.user)
                .filter(participants=other)
                .first()
            )
        if channel is None:
            channel = ChatChannel.objects.create(related_product=product)
            channel.participants.add(request.user, other)
        elif product and channel.related_product_id is None:
            channel.related_product = product
            channel.save(update_fields=["related_product"])

        return Response(
            {
                "success": True,
                "channel": ChatChannelSerializer(
                    channel, context={"request": request}
                ).data,
            },
            status=201,
        )


class StaffRecipientsView(APIView):
    """GET /api/v1/chat/staff-recipients/ — eligible staff only."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in (
            Role.USER_ADMIN,
            Role.FINANCIAL_MANAGER,
            Role.SUPER_ADMIN,
        ):
            raise PermissionDenied("Staff messaging is only available to staff.")
        recipients = eligible_staff_recipients(
            request.user, request.query_params.get("search", "")
        )
        return Response(
            {
                "results": [
                    {
                        "id": str(user.pk),
                        "full_name": user.full_name,
                        "role": user.role,
                        "role_display": user.get_role_display(),
                        "location": user.location,
                        "scope": (
                            "Nationwide"
                            if getattr(user, "administrative_scope", None)
                            and user.administrative_scope.level == "GLOBAL"
                            else str(user.administrative_scope.location)
                            if getattr(user, "administrative_scope", None)
                            and user.administrative_scope.location_id
                            else user.location
                        ),
                    }
                    for user in recipients
                ]
            }
        )


class ChannelMessagesViewSet(
    mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet
):
    """GET/POST /api/v1/chat/channels/{channelID}/messages/ — message history."""

    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]

    def get_channel(self):
        """Return the addressed channel, or 404 when the caller is not a member.

        ``IsChatParticipant`` cannot be relied on here: a DRF list route never
        calls ``get_object()``, so object permissions would silently be skipped
        and a non-member could post into someone else's conversation.
        """
        channel = (
            ChatChannel.objects.filter(
                id=self.kwargs.get("channel_pk"), participants=self.request.user
            )
            .prefetch_related("participants")
            .first()
        )
        if channel is None or not can_access_channel(self.request.user, channel):
            raise NotFound("Channel not found.")
        return channel

    def get_queryset(self):
        return (
            Message.objects.filter(
                channel=self.get_channel(),
            )
            .filter(
                Q(moderation_status=MessageModerationStatus.APPROVED)
                | Q(sender=self.request.user)
            )
            .select_related("sender")
            .order_by("sent_at")
        )

    def create(self, request, *args, **kwargs):
        channel = self.get_channel()
        settings = PlatformSettings.load()
        if not settings.text_messaging_enabled:
            raise PermissionDenied("Messaging is temporarily unavailable.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = dict(serializer.validated_data)
        kind = validated.pop("kind", MessageKind.TEXT)
        if kind == MessageKind.VOICE and not settings.voice_messaging_enabled:
            raise PermissionDenied("Voice messaging is temporarily unavailable.")
        audio = validated.pop("audio", None)
        audio_content_type = validated.pop("audio_content_type", "")
        pending_review = False
        if kind == MessageKind.VOICE:
            try:
                transcript = transcribe_voice(audio)
            except VoiceTranscriptionError:
                pending_review = True
            else:
                if not transcript.strip():
                    pending_review = True
                elif contains_restricted_content(transcript):
                    raise ValidationError(
                        {
                            "audio": (
                                "This voice message contains restricted contact or "
                                "location information. Please record a corrected message."
                            )
                        }
                    )
            audio.seek(0)
            status = (
                MessageModerationStatus.PENDING_REVIEW
                if pending_review
                else MessageModerationStatus.APPROVED
            )
            with transaction.atomic():
                message = Message.objects.create(
                    channel=channel,
                    sender=request.user,
                    content="",
                    kind=MessageKind.VOICE,
                    audio_file=audio,
                    audio_content_type=audio_content_type,
                    moderation_status=status,
                )
                if not pending_review:
                    channel.last_message_at = message.sent_at
                    channel.save(update_fields=["last_message_at"])
        else:
            message = serializer.save(sender=request.user, channel=channel)
            channel.last_message_at = message.sent_at
            channel.save(update_fields=["last_message_at"])

        # Participant notifications come from the message_received domain event
        # (doc 4.11.2); the view only fans the message out over the socket.
        if not pending_review:
            push_chat_event(
                str(channel.id),
                {
                    "type": "chat.message",
                    "channel_id": str(channel.id),
                    "message": MessageSerializer(
                        message, context={"request": request}
                    ).data,
                },
            )
        return Response(
            {
                "success": True,
                "message": MessageSerializer(
                    message, context={"request": request}
                ).data,
            },
            status=202 if pending_review else 201,
        )


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
class MarkChannelReadView(viewsets.ViewSet):
    """POST /api/v1/chat/channels/{channelID}/mark-read/"""

    permission_classes = [IsAuthenticated]

    def create(self, request, channel_pk=None):
        channel = (
            ChatChannel.objects.filter(id=channel_pk, participants=request.user)
            .prefetch_related("participants")
            .first()
        )
        if channel is None or not can_access_channel(request.user, channel):
            return Response({"success": False, "error": "Channel not found."}, status=404)
        updated = Message.objects.filter(
            channel_id=channel_pk,
            moderation_status=MessageModerationStatus.APPROVED,
        ).exclude(sender=request.user).update(is_read=True)
        return Response({"success": True, "updated": updated})


class ChatMessageAudioView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, channel_pk, message_pk):
        channel = (
            ChatChannel.objects.filter(pk=channel_pk)
            .prefetch_related("participants")
            .first()
        )
        if channel is None:
            raise NotFound("Voice message not found.")
        is_participant = channel.participants.filter(pk=request.user.pk).exists()
        if (
            is_participant and not can_access_channel(request.user, channel)
        ) or (
            not is_participant and not can_moderate_voice(request.user, channel)
        ):
            raise NotFound("Voice message not found.")
        message = get_object_or_404(
            Message.objects.filter(channel=channel, kind=MessageKind.VOICE),
            pk=message_pk,
        )
        if (
            message.moderation_status == MessageModerationStatus.BLOCKED
            or not message.audio_file
            or (
                message.moderation_status == MessageModerationStatus.PENDING_REVIEW
                and message.sender_id != request.user.pk
                and not can_moderate_voice(request.user, channel)
            )
            or (
                message.moderation_status == MessageModerationStatus.APPROVED
                and not is_participant
            )
        ):
            raise NotFound("Voice message not found.")
        response = FileResponse(
            message.audio_file.open("rb"),
            content_type=message.audio_content_type or "application/octet-stream",
        )
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "default-src 'none'"
        response["Content-Disposition"] = 'inline; filename="voice-message"'
        return response


class VoiceMessageModerationViewSet(
    mixins.ListModelMixin, viewsets.GenericViewSet
):
    serializer_class = MessageSerializer

    def get_permissions(self):
        return [
            IsAuthenticatedRole(
                (Role.USER_ADMIN, Role.FINANCIAL_MANAGER, Role.SUPER_ADMIN)
            )
        ]

    def get_queryset(self):
        queryset = (
            Message.objects.filter(
                kind=MessageKind.VOICE,
                moderation_status=MessageModerationStatus.PENDING_REVIEW,
            )
            .select_related("sender", "channel")
            .prefetch_related("channel__participants")
            .order_by("sent_at")
        )
        if self.request.user.role == Role.USER_ADMIN:
            from registrations.services import users_visible_to_admin

            visible_ids = users_visible_to_admin(self.request.user).values("pk")
            queryset = (
                queryset.annotate(
                    outside_scope_count=Count(
                        "channel__participants",
                        filter=~Q(channel__participants__pk__in=visible_ids),
                    )
                )
                .filter(outside_scope_count=0)
            )
        return queryset

    @action(detail=True, methods=["post"], url_path="review")
    def review(self, request, pk=None):
        decision = request.data.get("decision")
        reason = (request.data.get("reason") or "").strip()
        if decision not in ("APPROVE", "BLOCK"):
            raise ValidationError({"decision": "Choose APPROVE or BLOCK."})
        if not reason or len(reason) > 500:
            raise ValidationError(
                {"reason": "Provide a reason of 1 to 500 characters."}
            )
        if contains_restricted_content(reason):
            raise ValidationError(
                {"reason": "Do not include private contact details in the reason."}
            )

        with transaction.atomic():
            message = (
                Message.objects.select_for_update()
                .select_related("sender", "channel")
                .prefetch_related("channel__participants")
                .filter(pk=pk)
                .first()
            )
            if message is None or not can_moderate_voice(
                request.user, message.channel
            ):
                raise NotFound("Voice message not found.")
            if (
                message.kind != MessageKind.VOICE
                or message.moderation_status
                != MessageModerationStatus.PENDING_REVIEW
            ):
                raise ValidationError(
                    {"status": "This voice message has already been reviewed."}
                )
            previous_status = message.moderation_status
            audio_storage = message.audio_file.storage
            audio_name = message.audio_file.name
            if decision == "APPROVE":
                message.moderation_status = MessageModerationStatus.APPROVED
                message.channel.last_message_at = timezone.now()
                message.channel.save(update_fields=["last_message_at"])
            else:
                message.moderation_status = MessageModerationStatus.BLOCKED
                message.audio_file = ""
            message.save(update_fields=["moderation_status", "audio_file"])
            if decision == "BLOCK" and audio_name:
                transaction.on_commit(lambda: audio_storage.delete(audio_name))
            AuditLog.objects.create(
                actor=request.user,
                action="voice_message_reviewed",
                target=str(message.pk),
                detail=(
                    f"status: {previous_status} -> {message.moderation_status}; "
                    f"reason: {reason}"
                ),
            )

        participant_ids = list(
            message.channel.participants.exclude(pk=message.sender_id).values_list(
                "pk", flat=True
            )
        )
        if decision == "APPROVE":
            serialized = MessageSerializer(
                message, context={"request": request}
            ).data
            push_chat_event(
                str(message.channel_id),
                {
                    "type": "chat.message",
                    "channel_id": str(message.channel_id),
                    "message": serialized,
                },
            )
            notify(
                user_ids=participant_ids,
                type="MESSAGE",
                message="A voice message passed moderation and was delivered.",
                actor=request.user,
                target_url=f"/chat?channel={message.channel_id}",
            )
        else:
            notify(
                user_ids=[message.sender_id],
                type="MESSAGE",
                message=(
                    "Your voice message was blocked during moderation. "
                    "Please record a corrected message."
                ),
                actor=request.user,
                target_url=f"/chat?channel={message.channel_id}",
            )
        return Response(
            {
                "success": True,
                "message": MessageSerializer(
                    message, context={"request": request}
                ).data,
            }
        )
