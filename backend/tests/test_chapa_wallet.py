"""Chapa test-mode wallet funding and financial approval coverage."""

import hashlib
import hmac
import json
from decimal import Decimal
from io import BytesIO
from urllib.error import HTTPError

import pytest
from django.conf import settings
from rest_framework.exceptions import APIException

from payments.models import FundingStatus, Wallet, WalletTransaction

pytestmark = pytest.mark.django_db


@pytest.fixture
def chapa_configuration(settings, monkeypatch):
    settings.CHAPA_TEST_MODE = True
    settings.CHAPA_SECRET_KEY = "CHASECK_TEST-unit-test-key"
    settings.CHAPA_WEBHOOK_SECRET = "unit-test-webhook-secret"
    monkeypatch.setattr(
        "payments.chapa._chapa_request",
        lambda method, path, payload=None: {
            "status": "success",
            "data": {"checkout_url": "https://checkout.chapa.co/test"},
        },
    )


def test_chapa_initialization_is_test_only_and_idempotent(
    api, wholesaler, chapa_configuration, monkeypatch
):
    calls = []

    def initialize(method, path, payload=None):
        calls.append((method, path, payload))
        return {
            "status": "success",
            "data": {"checkout_url": "https://checkout.chapa.co/test"},
        }

    monkeypatch.setattr("payments.chapa._chapa_request", initialize)
    api.force_authenticate(user=wholesaler)
    payload = {"amount": "125.50"}
    first = api.post(
        "/api/v1/wallet/funding/chapa/",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="deposit-once",
    )
    retry = api.post(
        "/api/v1/wallet/funding/chapa/",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="deposit-once",
    )

    assert first.status_code == 201, first.data
    assert retry.status_code == 200, retry.data
    assert first.data["id"] == retry.data["id"]
    assert first.data["status"] == FundingStatus.AWAITING_PAYMENT
    assert first.data["payment_mode"] == "TEST"
    assert first.data["checkout_url"] == "https://checkout.chapa.co/test"
    assert calls[0][0:2] == ("POST", "/transaction/initialize")
    assert calls[0][2]["currency"] == "ETB"
    assert calls[0][2]["tx_ref"] == first.data["external_reference"]
    assert len(calls[0][2]["customization"]["title"]) <= 16
    assert len(calls) == 1
    assert Wallet.objects.get(user=wholesaler).available_balance == Decimal("100000.00")
    assert not WalletTransaction.objects.filter(wallet__user=wholesaler).exists()


def test_chapa_checkout_does_not_require_optional_webhook_secret(
    api, wholesaler, chapa_configuration, settings
):
    settings.CHAPA_WEBHOOK_SECRET = ""
    api.force_authenticate(user=wholesaler)
    response = api.post(
        "/api/v1/wallet/funding/chapa/",
        {"amount": "15.00"},
        format="json",
    )
    assert response.status_code == 201, response.data
    assert response.data["checkout_url"] == "https://checkout.chapa.co/test"


def test_chapa_checkout_cors_allows_idempotency_header(api):
    response = api.options(
        "/api/v1/wallet/funding/chapa/",
        HTTP_ORIGIN="http://localhost:3000",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS=(
            "authorization,content-type,idempotency-key"
        ),
    )
    assert response.status_code == 200
    assert "idempotency-key" in response["Access-Control-Allow-Headers"]


def test_chapa_provider_validation_error_is_actionable_and_redacts_secret(
    settings, monkeypatch
):
    settings.CHAPA_TEST_MODE = True
    settings.CHAPA_SECRET_KEY = "CHASECK_TEST-do-not-log-this"

    def reject_request(*args, **kwargs):
        raise HTTPError(
            "https://api.chapa.co/v1/transaction/initialize",
            400,
            "Bad Request",
            {},
            BytesIO(
                b'{"data":{"errors":{"callback_url":["Invalid callback URL"]}},'
                b'"token":"CHASECK_TEST-do-not-log-this"}'
            ),
        )

    monkeypatch.setattr("payments.chapa.urlopen", reject_request)
    from payments.chapa import _chapa_request

    with pytest.raises(APIException, match="HTTP 400") as error:
        _chapa_request("POST", "/transaction/initialize", {})
    assert "Invalid callback URL" in str(error.value.detail)
    assert "do-not-log-this" not in str(error.value.detail)


def test_provider_rejected_initialization_is_recorded_as_failed(
    api, wholesaler, chapa_configuration, monkeypatch
):
    from payments.chapa import ChapaGatewayError

    def reject_request(*args, **kwargs):
        try:
            raise HTTPError(
                "https://api.chapa.co/v1/transaction/initialize",
                400,
                "Bad Request",
                {},
                BytesIO(b'{"message":"Invalid customer email"}'),
            )
        except HTTPError as exc:
            raise ChapaGatewayError("Chapa rejected customer information.") from exc

    monkeypatch.setattr("payments.chapa._chapa_request", reject_request)
    api.force_authenticate(user=wholesaler)
    response = api.post(
        "/api/v1/wallet/funding/chapa/",
        {"amount": "10000.00"},
        format="json",
    )
    assert response.status_code == 502
    funding = Wallet.objects.get(user=wholesaler).funding_requests.get()
    assert funding.status == FundingStatus.FAILED
    assert funding.provider_status == "INITIALIZATION_REJECTED_400"
    assert funding.checkout_url == ""
    assert Wallet.objects.get(user=wholesaler).available_balance == Decimal("100000.00")


def test_wallet_credits_only_after_chapa_verification_and_finance_approval(
    api, wholesaler, retailer, wholesaler_product, financial_manager,
    chapa_configuration, monkeypatch,
):
    api.force_authenticate(user=wholesaler)
    created = api.post(
        "/api/v1/wallet/funding/chapa/",
        {"amount": "125.50"},
        format="json",
    )
    assert created.status_code == 201, created.data
    reference = created.data["external_reference"]

    monkeypatch.setattr(
        "payments.chapa._chapa_request",
        lambda method, path, payload=None: {
            "status": "success",
            "data": {
                "status": "success",
                "tx_ref": reference,
                "amount": "125.50",
                "currency": "ETB",
                "mode": "test",
            },
        },
    )
    verified = api.post(
        f"/api/v1/wallet/funding/{created.data['id']}/verify/",
        format="json",
    )
    assert verified.status_code == 200, verified.data
    assert verified.data["status"] == FundingStatus.AWAITING_APPROVAL
    assert verified.data["payment_verified"] is True
    assert Wallet.objects.get(user=wholesaler).available_balance == Decimal("100000.00")

    api.force_authenticate(user=financial_manager)
    approved = api.post(
        f"/api/v1/wallet/funding/{created.data['id']}/review/",
        {"approve": True, "notes": "Test transaction confirmed"},
        format="json",
    )
    assert approved.status_code == 200, approved.data
    assert approved.data["funding_request"]["status"] == FundingStatus.APPROVED
    assert approved.data["funding_request"]["reviewed_by_name"] == financial_manager.full_name
    wallet = Wallet.objects.get(user=wholesaler)
    assert wallet.available_balance == Decimal("100125.50")
    assert WalletTransaction.objects.filter(
        wallet=wallet, transaction_type="FUNDING"
    ).count() == 1

    duplicate = api.post(
        f"/api/v1/wallet/funding/{created.data['id']}/review/",
        {"approve": True, "notes": "Duplicate"},
        format="json",
    )
    assert duplicate.status_code == 400
    assert wallet.transactions.filter(transaction_type="FUNDING").count() == 1

    api.force_authenticate(user=retailer)
    listing = api.get(f"/api/v1/products/wholesaler-listings/{wholesaler_product.id}/")
    assert listing.status_code == 200, listing.data
    assert listing.data["owner_financially_verified"] is True

    assert not retailer.financially_verified
    assert wholesaler.financially_verified


def test_chapa_amount_mismatch_is_not_approvable(
    api, wholesaler, financial_manager, chapa_configuration, monkeypatch
):
    api.force_authenticate(user=wholesaler)
    created = api.post(
        "/api/v1/wallet/funding/chapa/",
        {"amount": "125.50"},
        format="json",
    )
    reference = created.data["external_reference"]
    monkeypatch.setattr(
        "payments.chapa._chapa_request",
        lambda method, path, payload=None: {
            "status": "success",
            "data": {
                "status": "success",
                "tx_ref": reference,
                "amount": "125.49",
                "currency": "ETB",
                "mode": "test",
            },
        },
    )
    failed = api.post(
        f"/api/v1/wallet/funding/{created.data['id']}/verify/",
        format="json",
    )
    assert failed.status_code == 200
    assert failed.data["status"] == FundingStatus.FAILED
    assert failed.data["payment_verified"] is False
    assert Wallet.objects.get(user=wholesaler).available_balance == Decimal("100000.00")

    api.force_authenticate(user=financial_manager)
    rejected_approval = api.post(
        f"/api/v1/wallet/funding/{created.data['id']}/review/",
        {"approve": True, "notes": ""},
        format="json",
    )
    assert rejected_approval.status_code == 400
    assert not WalletTransaction.objects.filter(wallet__user=wholesaler).exists()


def test_webhook_signature_required_and_duplicate_delivery_is_safe(
    api, wholesaler, chapa_configuration, monkeypatch
):
    api.force_authenticate(user=wholesaler)
    created = api.post(
        "/api/v1/wallet/funding/chapa/",
        {"amount": "40.00"},
        format="json",
    )
    reference = created.data["external_reference"]
    payload = {
        "event": "charge.success",
        "data": {"tx_ref": reference},
    }
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    secret = settings.CHAPA_WEBHOOK_SECRET.encode("utf-8")
    signature_v1 = hmac.new(secret, secret, hashlib.sha256).hexdigest()
    signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
    verification_calls = []

    def verify(method, path, payload=None):
        verification_calls.append((method, path))
        return {
            "status": "success",
            "data": {
                "status": "success",
                "tx_ref": reference,
                "amount": "40.00",
                "currency": "ETB",
                "mode": "test",
            },
        }

    monkeypatch.setattr("payments.chapa._chapa_request", verify)
    invalid = api.generic(
        "POST",
        "/api/v1/wallet/chapa/webhook/",
        data=body,
        content_type="application/json",
    )
    assert invalid.status_code == 403
    assert not verification_calls

    for signature_header in (
        {"HTTP_X_CHAPA_SIGNATURE_V2": signature},
        {"HTTP_X_CHAPA_SIGNATURE": signature_v1},
    ):
        response = api.generic(
            "POST",
            "/api/v1/wallet/chapa/webhook/",
            data=body,
            content_type="application/json",
            **signature_header,
        )
        assert response.status_code == 200, response.data

    assert verification_calls == [
        ("GET", f"/transaction/verify/{reference}")
    ]
    funding = Wallet.objects.get(user=wholesaler).funding_requests.get()
    assert funding.status == FundingStatus.AWAITING_APPROVAL
    assert WalletTransaction.objects.filter(wallet=funding.wallet).count() == 0
