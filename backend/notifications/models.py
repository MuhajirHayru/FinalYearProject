import uuid

from django.conf import settings
from django.db import models


class NotificationType(models.TextChoices):
    REGISTRATION = "REGISTRATION", "Registration"
    APPROVAL = "APPROVAL", "Approval"
    REJECTION = "REJECTION", "Rejection"
    MESSAGE = "MESSAGE", "Message"
    PAYMENT = "PAYMENT", "Payment"
    ORDER = "ORDER", "Order"
    PRODUCT = "PRODUCT", "Product"
    SYSTEM = "SYSTEM", "System"


class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="actions_caused",
    )
    type = models.CharField(max_length=30, choices=NotificationType.choices, default=NotificationType.SYSTEM)
    message = models.TextField()
    target_url = models.CharField(max_length=500, blank=True, default="")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.recipient.full_name}: {self.message[:50]}"
