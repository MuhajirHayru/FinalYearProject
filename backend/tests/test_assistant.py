import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status

from assistant.models import AssistantConversation, AssistantMessage
from assistant.provider import AssistantProviderError, _run_tool, get_assistant_reply
from products.models import Product, ProductStatus, ProductType

pytestmark = pytest.mark.django_db


def test_conversation_api_requires_authentication(api):
    response = api.get("/api/v1/assistant/conversations/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_conversation_and_message_history_are_private(api, farmer, farmer_b):
    api.force_authenticate(user=farmer)
    created = api.post(
        "/api/v1/assistant/conversations/", {"language": "am"}, format="json"
    )
    assert created.status_code == status.HTTP_201_CREATED
    conversation_id = created.data["id"]
    AssistantMessage.objects.create(
        conversation_id=conversation_id, role="assistant", content="Private response"
    )

    api.force_authenticate(user=farmer_b)
    assert api.get(
        f"/api/v1/assistant/conversations/{conversation_id}/messages/"
    ).status_code == status.HTTP_404_NOT_FOUND
    assert api.delete(
        f"/api/v1/assistant/conversations/{conversation_id}/"
    ).status_code == status.HTTP_404_NOT_FOUND
    assert AssistantConversation.objects.filter(pk=conversation_id).exists()


def test_message_endpoint_uses_server_history_and_persists_reply(
    api, farmer, monkeypatch
):
    conversation = AssistantConversation.objects.create(owner=farmer)
    previous = AssistantMessage.objects.create(
        conversation=conversation, role="user", content="Previous question"
    )
    calls = []

    def reply(user, language, history):
        calls.append((user, language, history))
        return "A helpful answer"

    monkeypatch.setattr("assistant.views.get_assistant_reply", reply)
    api.force_authenticate(user=farmer)
    response = api.post(
        f"/api/v1/assistant/conversations/{conversation.id}/messages/",
        {"content": "New question", "language": "en"},
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED, response.data
    assert calls[0][0] == farmer
    assert calls[0][1] == "en"
    assert calls[0][2] == [
        {"role": "user", "content": "Previous question"},
        {"role": "user", "content": "New question"},
    ]
    assert response.data["assistant_message"]["content"] == "A helpful answer"
    assert response.data["user_message"]["content"] == "New question"
    assert conversation.messages.filter(pk=previous.pk).exists()


def test_message_validation_and_provider_failure_are_explicit(api, farmer, monkeypatch):
    conversation = AssistantConversation.objects.create(owner=farmer)
    api.force_authenticate(user=farmer)
    url = f"/api/v1/assistant/conversations/{conversation.id}/messages/"
    assert api.post(url, {"content": "   "}, format="json").status_code == 400
    assert api.post(url, {"content": "x" * 2001}, format="json").status_code == 400

    def fail(*args, **kwargs):
        raise AssistantProviderError("Provider unavailable")

    monkeypatch.setattr("assistant.views.get_assistant_reply", fail)
    response = api.post(url, {"content": "Help"}, format="json")
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.data["error"] == "Provider unavailable"
    assert conversation.messages.count() == 0


def test_marketplace_tool_is_role_scoped_and_read_only(
    farmer, farmer_product, farmer_b, wholesaler, retailer, wholesaler_product
):
    farmer_product.status = ProductStatus.ACTIVE
    farmer_product.save(update_fields=["status"])
    result = _run_tool(
        "search_marketplace", {"query": "Tomato"}, wholesaler
    )
    assert {listing["title"] for listing in result["listings"]} == {
        "Tomato",
        "Wholesale Tomato",
    }
    wholesaler_listings = _run_tool(
        "search_marketplace", {"query": "Wholesale"}, wholesaler
    )
    assert [listing["title"] for listing in wholesaler_listings["listings"]] == [
        "Wholesale Tomato"
    ]

    farmer_other_listing = Product.objects.create(
        title="Tomato from another farmer",
        quantity=5,
        price_per_unit=5,
        owner=farmer_b,
        product_type=ProductType.FARMER_LISTING,
        status=ProductStatus.ACTIVE,
    )
    farmer_listings = _run_tool("search_marketplace", {"query": "Tomato"}, farmer)
    assert [listing["title"] for listing in farmer_listings["listings"]] == ["Tomato"]
    no_match = _run_tool("search_marketplace", {"query": "Tomato"}, retailer)
    assert [listing["title"] for listing in no_match["listings"]] == [
        "Wholesale Tomato"
    ]

    assert Product.objects.filter(pk=farmer_product.pk).exists()
    assert Product.objects.filter(pk=farmer_other_listing.pk).exists()


def test_order_and_wallet_tools_only_return_actors_own_records(
    farmer, wholesaler, farmer_b, order
):
    farmer_orders = _run_tool("my_recent_orders", {}, farmer)
    assert [row["reference"] for row in farmer_orders["orders"]] == [order.reference]
    outsider_orders = _run_tool("my_recent_orders", {}, farmer_b)
    assert outsider_orders["orders"] == []
    wallet = _run_tool("my_wallet_summary", {}, wholesaler)
    assert wallet["wallet"]["currency"] == "ETB"
    assert _run_tool("my_wallet_summary", {}, farmer)["wallet"] is None
    with pytest.raises(AssistantProviderError):
        _run_tool("my_recent_orders", {"user_id": str(farmer.id)}, farmer)


def test_provider_requires_server_configuration(farmer):
    with override_settings(GROQ_API_KEY="", GROQ_CHAT_MODEL=""):
        with pytest.raises(AssistantProviderError, match="Groq API key"):
            get_assistant_reply(farmer, "en", [{"role": "user", "content": "Hello"}])
    with override_settings(GROQ_API_KEY="configured", GROQ_CHAT_MODEL=""):
        with pytest.raises(AssistantProviderError, match="tool calling"):
            get_assistant_reply(farmer, "en", [{"role": "user", "content": "Hello"}])


def test_transcription_validation(api, farmer):
    api.force_authenticate(user=farmer)
    assert api.post(
        "/api/v1/assistant/transcribe/",
        {"language": "en"},
        format="multipart",
    ).status_code == 400
    response = api.post(
        "/api/v1/assistant/transcribe/",
        {
            "language": "en",
            "audio": SimpleUploadedFile(
                "not-audio.txt", b"not audio", content_type="text/plain"
            ),
        },
        format="multipart",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_transcription_reports_missing_provider_configuration(api, farmer):
    api.force_authenticate(user=farmer)
    with override_settings(GROQ_API_KEY=""):
        response = api.post(
            "/api/v1/assistant/transcribe/",
            {
                "language": "auto",
                "audio": SimpleUploadedFile(
                    "sample.webm", b"audio data", content_type="audio/webm"
                ),
            },
            format="multipart",
        )
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    message = response.data["error"].lower()
    assert "type" in message or "configured" in message
