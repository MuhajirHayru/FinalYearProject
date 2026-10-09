"""Server-side Chapa hosted-checkout integration for test-mode wallet deposits."""

import hashlib
import hmac
import json
import logging
import re
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from rest_framework.exceptions import APIException, ValidationError

from .models import FundingStatus, WalletFundingRequest

logger = logging.getLogger(__name__)


class ChapaUnavailable(APIException):
    status_code = 503
    default_detail = "Chapa test payments are not configured or are temporarily unavailable."
    default_code = "chapa_unavailable"


class ChapaGatewayError(APIException):
    status_code = 502
    default_detail = "Chapa could not process this payment request."
    default_code = "chapa_gateway_error"


def _config(*, require_webhook=False):
    if not settings.CHAPA_TEST_MODE:
        raise ChapaUnavailable("Only Chapa test-mode transactions are enabled.")
    secret_key = settings.CHAPA_SECRET_KEY
    if not secret_key or not secret_key.startswith("CHASECK_TEST-"):
        raise ChapaUnavailable(
            "Configure a Chapa test secret key before starting test payments."
        )
    webhook_secret = settings.CHAPA_WEBHOOK_SECRET
    if require_webhook and not webhook_secret:
        raise ChapaUnavailable(
            "Configure the Chapa webhook secret before enabling payment callbacks."
        )
    return secret_key, webhook_secret


def validate_configuration(*, require_webhook=False):
    _config(require_webhook=require_webhook)


def _provider_error_message(response):
    messages = []

    def collect(value, path=()):
        if isinstance(value, dict):
            for key, item in value.items():
                collect(item, (*path, str(key)))
        elif isinstance(value, list):
            for item in value:
                collect(item, path)
        elif isinstance(value, str) and path:
            message = re.sub(r"[\r\n\t]+", " ", value).strip()
            message = message.replace(settings.CHAPA_SECRET_KEY, "[redacted]")
            message = re.sub(
                r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b",
                "[redacted email]",
                message,
            )
            message = re.sub(
                r"(?<!\d)\+?\d(?:[\d -]{7,}\d)(?!\d)",
                "[redacted number]",
                message,
            )
            if message:
                messages.append(f"{'.'.join(path)}: {message}")

    collect(response)
    return "; ".join(messages)[:240]


def _chapa_request(method, path, payload=None):
    secret_key, _ = _config()
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        f"{settings.CHAPA_API_BASE_URL.rstrip('/')}/{path.lstrip('/')}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=settings.CHAPA_TIMEOUT_SECONDS) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raw_response = exc.read().decode("utf-8", errors="replace")
        try:
            provider_response = json.loads(raw_response)
        except json.JSONDecodeError:
            provider_response = {}
        provider_message = _provider_error_message(provider_response)
        provider_fields = (
            sorted(provider_response.keys())
            if isinstance(provider_response, dict)
            else []
        )
        logger.warning(
            "Chapa API error response metadata: content_type=%s body_bytes=%s fields=%s",
            exc.headers.get("Content-Type") if exc.headers else "unknown",
            len(raw_response.encode("utf-8")),
            provider_fields,
        )
        if not provider_message:
            provider_message = "Chapa returned an HTTP error without a readable message."
        logger.warning(
            "Chapa API rejected %s request with HTTP %s: %s",
            method,
            exc.code,
            provider_message,
        )
        raise ChapaGatewayError(
            f"Chapa rejected the request (HTTP {exc.code}): {provider_message}"
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        logger.warning("Chapa API transport failed (%s)", type(exc).__name__)
        raise ChapaGatewayError(
            "Could not reach Chapa. Check backend network access and retry."
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.warning("Chapa API returned an invalid JSON response.")
        raise ChapaGatewayError(
            "Chapa returned an invalid response. Please retry later."
        ) from exc
    if not isinstance(result, dict):
        logger.warning("Chapa API returned a JSON response with an invalid shape.")
        raise ChapaGatewayError()
    return result


def initialize_checkout(funding):
    user = funding.wallet.user
    names = user.full_name.strip().split(maxsplit=1)
    payload = {
        "amount": str(funding.amount),
        "currency": funding.wallet.currency,
        "email": user.email,
        "first_name": names[0] if names else user.email,
        "last_name": names[1] if len(names) > 1 else names[0] if names else "",
        "tx_ref": funding.external_reference,
        "callback_url": settings.CHAPA_CALLBACK_URL,
        "return_url": (
            f"{settings.FRONTEND_BASE_URL.rstrip('/')}/wallet"
            f"?funding={funding.pk}"
        ),
        "customization": {
            "title": "GreenPath Wallet",
            "description": "Test-mode wallet funding",
        },
    }
    if re.fullmatch(r"0[79]\d{8}", user.phone or ""):
        payload["phone_number"] = user.phone

    response = _chapa_request("POST", "/transaction/initialize", payload)
    data = response.get("data")
    checkout_url = data.get("checkout_url") if isinstance(data, dict) else None
    if response.get("status") != "success" or not isinstance(checkout_url, str):
        raise ChapaGatewayError()
    if not checkout_url.startswith("https://"):
        raise ChapaGatewayError()
    return checkout_url


def _apply_verification(funding_id, provider_data):
    tx_ref = str(provider_data.get("tx_ref") or "")
    provider_status = str(provider_data.get("status") or "").strip().lower()
    currency = str(provider_data.get("currency") or "").strip().upper()
    try:
        amount = Decimal(str(provider_data.get("amount")))
    except (InvalidOperation, TypeError, ValueError):
        amount = None

    with transaction.atomic():
        funding = WalletFundingRequest.objects.select_for_update().select_related(
            "wallet"
        ).get(pk=funding_id)
        if funding.status in (
            FundingStatus.AWAITING_APPROVAL,
            FundingStatus.APPROVED,
            FundingStatus.REJECTED,
        ):
            return funding, False
        if funding.status not in (
            FundingStatus.AWAITING_PAYMENT,
            FundingStatus.PAYMENT_VERIFICATION_PENDING,
        ):
            return funding, False

        mode = provider_data.get("mode", "test")
        mismatch = (
            tx_ref != funding.external_reference
            or amount != funding.amount
            or currency != funding.wallet.currency.upper()
            or not isinstance(mode, str)
            or mode.lower() != "test"
        )
        funding.provider_status = provider_status[:32]
        funding.verified_amount = amount
        funding.verified_currency = currency[:3]
        if provider_data.get("id") is not None:
            funding.provider_transaction_id = str(provider_data["id"])[:255]

        if mismatch:
            funding.status = FundingStatus.FAILED
            funding.payment_verified = False
            funding.review_notes = (
                "Chapa verification did not match the deposit reference, amount, "
                "currency, or test mode."
            )
        elif provider_status == "success":
            funding.status = FundingStatus.AWAITING_APPROVAL
            funding.payment_verified = True
            funding.payment_verified_at = timezone.now()
        elif provider_status in ("pending", "processing", "initiated"):
            funding.status = FundingStatus.PAYMENT_VERIFICATION_PENDING
            funding.payment_verified = False
        else:
            funding.status = FundingStatus.FAILED
            funding.payment_verified = False

        funding.save(
            update_fields=[
                "status",
                "provider_status",
                "verified_amount",
                "verified_currency",
                "provider_transaction_id",
                "payment_verified",
                "payment_verified_at",
                "review_notes",
            ]
        )
        return funding, funding.status == FundingStatus.AWAITING_APPROVAL


def verify_funding(funding):
    if funding.status in (
        FundingStatus.AWAITING_APPROVAL,
        FundingStatus.APPROVED,
        FundingStatus.REJECTED,
    ):
        return funding, False
    if funding.status not in (
        FundingStatus.AWAITING_PAYMENT,
        FundingStatus.PAYMENT_VERIFICATION_PENDING,
    ):
        raise ValidationError({"status": "This deposit cannot be verified."})
    _config()
    response = _chapa_request(
        "GET",
        f"/transaction/verify/{quote(funding.external_reference, safe='')}",
    )
    data = response.get("data")
    if response.get("status") != "success" or not isinstance(data, dict):
        raise ChapaGatewayError()
    return _apply_verification(funding.pk, data)


def verify_webhook_signature(body, signature, signature_v2):
    _, webhook_secret = _config(require_webhook=True)
    webhook_secret_bytes = webhook_secret.encode("utf-8")
    expected_v1 = hmac.new(
        webhook_secret_bytes,
        webhook_secret_bytes,
        hashlib.sha256,
    ).hexdigest()
    expected_v2 = hmac.new(
        webhook_secret_bytes, body, hashlib.sha256
    ).hexdigest()

    def matches(value, expected):
        value = (value or "").strip()
        if value.lower().startswith("sha256="):
            value = value[7:]
        return bool(value) and hmac.compare_digest(value.lower(), expected.lower())

    return matches(signature, expected_v1) or matches(signature_v2, expected_v2)


def funding_from_webhook(body):
    try:
        event = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError("Invalid Chapa webhook payload.") from exc
    if not isinstance(event, dict):
        raise ValidationError("Invalid Chapa webhook payload.")
    data = event.get("data")
    tx_ref = data.get("tx_ref") if isinstance(data, dict) else None
    if not isinstance(tx_ref, str) or not tx_ref:
        raise ValidationError("Chapa webhook is missing its transaction reference.")
    return WalletFundingRequest.objects.select_related("wallet__user").filter(
        payment_method="Chapa", external_reference=tx_ref, payment_mode="TEST"
    ).first()
