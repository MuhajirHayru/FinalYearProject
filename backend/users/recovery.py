import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.mail import send_mail
from django.core.exceptions import ImproperlyConfigured


class RecoveryDeliveryError(RuntimeError):
    pass


def send_password_reset(user, channel, reset_url):
    if channel == "email":
        sent = send_mail(
            subject="Reset your Green Path password",
            message=(
                f"Hello {user.full_name},\n\n"
                "Use the link below to reset your password. It expires shortly "
                "and can only be used once.\n\n"
                f"{reset_url}\n\n"
                "If you did not request this, you can ignore this message."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        if sent != 1:
            raise RecoveryDeliveryError("The reset email was not accepted for delivery.")
        return

    if channel != "sms":
        raise ValueError("Unsupported password recovery channel.")
    if not re.fullmatch(r"\+[1-9]\d{7,14}", user.phone or ""):
        raise RecoveryDeliveryError("The account has no valid international phone number.")
    if not settings.AFRICASTALKING_USERNAME or not settings.AFRICASTALKING_API_KEY:
        raise ImproperlyConfigured("Africa's Talking credentials are not configured.")

    payload = {
        "username": settings.AFRICASTALKING_USERNAME,
        "to": user.phone,
        "message": f"Green Path password reset: {reset_url}",
    }
    if settings.AFRICASTALKING_SENDER_ID:
        payload["from"] = settings.AFRICASTALKING_SENDER_ID

    request = Request(
        "https://api.africastalking.com/version1/messaging",
        data=urlencode(payload).encode("ascii"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "apiKey": settings.AFRICASTALKING_API_KEY,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=settings.AFRICASTALKING_TIMEOUT_SECONDS) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        raise RecoveryDeliveryError("Africa's Talking could not send the reset SMS.") from exc

    message_data = result.get("SMSMessageData", {})
    recipients = message_data.get("Recipients", [])
    if (
        not recipients
        or any(
            str(recipient.get("status", "")).lower() not in ("success", "sent")
            for recipient in recipients
        )
    ):
        raise RecoveryDeliveryError("Africa's Talking did not accept the reset SMS.")
