import os
import uuid

from django.conf import settings
from django.db import models

from products.models import Product
from .storage import PrivateChatStorage


def private_voice_upload_path(instance, filename):
    extension = os.path.splitext(filename)[1].lower()
    return f"voice-messages/{uuid.uuid4().hex}{extension}"


class MessageKind(models.TextChoices):
    TEXT = "TEXT", "Text"
    VOICE = "VOICE", "Voice"


class MessageModerationStatus(models.TextChoices):
    APPROVED = "APPROVED", "Approved"
    PENDING_REVIEW = "PENDING_REVIEW", "Pending review"
    BLOCKED = "BLOCKED", "Blocked"


class ChatChannel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="chat_channels"
    )
    related_product = models.ForeignKey(
        Product, on_delete=models.SET_NULL, null=True, blank=True, related_name="chat_channels"
    )
    last_message_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chat_channels"
        ordering = ["-last_message_at", "-created_at"]

    def __str__(self):
        names = ", ".join(self.participants.values_list("full_name", flat=True))
        return f"Channel({names})"

    def get_unread_count(self, user):
        return self.messages.filter(
            is_read=False,
            moderation_status=MessageModerationStatus.APPROVED,
        ).exclude(sender=user).count()


class Message(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    channel = models.ForeignKey(
        ChatChannel, on_delete=models.CASCADE, related_name="messages"
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_messages"
    )
    content = models.TextField()
    kind = models.CharField(
        max_length=8, choices=MessageKind.choices, default=MessageKind.TEXT
    )
    audio_file = models.FileField(
        storage=PrivateChatStorage(),
        upload_to=private_voice_upload_path,
        blank=True,
    )
    audio_content_type = models.CharField(max_length=100, blank=True, default="")
    moderation_status = models.CharField(
        max_length=20,
        choices=MessageModerationStatus.choices,
        default=MessageModerationStatus.APPROVED,
    )
    sent_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        db_table = "messages"
        ordering = ["sent_at"]

    def __str__(self):
        return f"{self.sender.full_name}: {self.content[:40]}"
