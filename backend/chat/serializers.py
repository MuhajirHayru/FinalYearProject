from django.conf import settings
from django.db.models import Q
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from users.models import User
from users.serializers import PublicUserSerializer

from .models import (
    ChatChannel,
    Message,
    MessageKind,
    MessageModerationStatus,
)
from greenpath.privacy import contains_restricted_content, restricted_content_message


class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source="sender.full_name", read_only=True)
    sender_financially_verified = serializers.BooleanField(
        source="sender.financially_verified", read_only=True
    )
    content = serializers.CharField(required=False, allow_blank=True)
    kind = serializers.ChoiceField(
        choices=MessageKind.choices, required=False, default=MessageKind.TEXT
    )
    audio = serializers.FileField(required=False, write_only=True)
    audio_url = serializers.SerializerMethodField()
    moderation_status = serializers.ChoiceField(
        choices=MessageModerationStatus.choices, read_only=True
    )

    class Meta:
        model = Message
        fields = [
            "id", "channel", "sender", "sender_name",
            "sender_financially_verified", "content", "kind", "audio",
            "audio_url", "moderation_status", "sent_at", "is_read",
        ]
        # The channel comes from the nested route and the sender from the request
        # user, so neither may be supplied by the client.
        read_only_fields = [
            "id", "channel", "sender", "audio_url", "moderation_status",
            "sent_at", "is_read",
        ]

    def validate_content(self, value):
        content = value.strip()
        if contains_restricted_content(content):
            raise serializers.ValidationError(restricted_content_message())
        return content

    def validate(self, attrs):
        kind = attrs.get("kind", MessageKind.TEXT)
        audio = attrs.get("audio")
        content = (attrs.get("content") or "").strip()
        if kind == MessageKind.TEXT:
            if audio is not None:
                raise serializers.ValidationError(
                    {"audio": "Audio is only valid for a voice message."}
                )
            if not content:
                raise serializers.ValidationError(
                    {"content": "Enter a message before sending."}
                )
        else:
            if audio is None:
                raise serializers.ValidationError(
                    {"audio": "Record or select a voice message."}
                )
            max_bytes = getattr(settings, "CHAT_VOICE_MAX_BYTES", 10 * 1024 * 1024)
            if audio.size > max_bytes:
                raise serializers.ValidationError(
                    {"audio": "Voice messages must be 10 MB or smaller."}
                )
            content_type = (getattr(audio, "content_type", "") or "").split(";")[0]
            if content_type not in {
                "audio/webm",
                "audio/ogg",
                "audio/mp4",
                "audio/mpeg",
                "audio/wav",
                "audio/x-wav",
            }:
                raise serializers.ValidationError(
                    {"audio": "Use a supported audio recording format."}
                )
            audio.seek(0)
            header = audio.read(12)
            audio.seek(0)
            if content_type == "audio/webm":
                valid_signature = header.startswith(b"\x1a\x45\xdf\xa3")
            elif content_type == "audio/ogg":
                valid_signature = header.startswith(b"OggS")
            elif content_type == "audio/mp4":
                valid_signature = len(header) >= 8 and header[4:8] == b"ftyp"
            elif content_type == "audio/mpeg":
                valid_signature = header.startswith(b"ID3") or (
                    len(header) >= 2
                    and header[0] == 0xFF
                    and header[1] & 0xE0 == 0xE0
                )
            else:
                valid_signature = (
                    header.startswith(b"RIFF") and header[8:12] == b"WAVE"
                )
            if not valid_signature:
                raise serializers.ValidationError(
                    {"audio": "The uploaded file is not a valid supported audio format."}
                )
            attrs["audio_content_type"] = content_type
            attrs["content"] = ""
        return attrs

    def get_audio_url(self, message):
        if message.kind != MessageKind.VOICE or not message.audio_file:
            return None
        request = self.context.get("request")
        if request is None:
            return None
        if (
            message.moderation_status == MessageModerationStatus.PENDING_REVIEW
            and request.user.pk != message.sender_id
        ):
            from .access import can_moderate_voice

            if not can_moderate_voice(request.user, message.channel):
                return None
        if message.moderation_status == MessageModerationStatus.BLOCKED:
            return None
        return (
            f"/api/v1/chat/channels/{message.channel_id}/messages/"
            f"{message.pk}/audio/"
        )

class ChatChannelSerializer(serializers.ModelSerializer):
    participants = PublicUserSerializer(many=True, read_only=True)
    participant_ids = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        many=True,
        write_only=True,
        source="participants",
        required=False,
    )
    related_product_title = serializers.CharField(
        source="related_product.title", read_only=True, default=None
    )
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = ChatChannel
        fields = [
            "id", "participants", "participant_ids", "related_product",
            "related_product_title", "last_message_at", "created_at",
            "last_message", "unread_count",
        ]
        read_only_fields = ["id", "last_message_at", "created_at"]

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_last_message(self, obj):
        request = self.context.get("request")
        messages = obj.messages.filter(
            moderation_status=MessageModerationStatus.APPROVED
        )
        if request and request.user.is_authenticated:
            messages = obj.messages.filter(
                Q(moderation_status=MessageModerationStatus.APPROVED)
                | Q(sender=request.user)
            )
        msg = messages.order_by("-sent_at").first()
        if not msg:
            return None
        return {
            "content": (
                "Voice message awaiting review"
                if msg.moderation_status == MessageModerationStatus.PENDING_REVIEW
                else "Voice message blocked"
                if msg.moderation_status == MessageModerationStatus.BLOCKED
                else "Voice message"
                if msg.kind == MessageKind.VOICE
                else msg.content
            ),
            "sender_name": msg.sender.full_name,
            "sender_financially_verified": msg.sender.financially_verified,
            "kind": msg.kind,
            "moderation_status": msg.moderation_status,
            "sent_at": msg.sent_at,
        }

    @extend_schema_field(serializers.IntegerField)
    def get_unread_count(self, obj):
        request = self.context.get("request")
        if not request:
            return 0
        return obj.get_unread_count(request.user)
