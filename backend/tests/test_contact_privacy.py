import pytest

from payments.models import Order, OrderPaymentStatus, OrderStatus
from users.models import AuditLog

pytestmark = pytest.mark.django_db


def test_marketplace_product_uses_coarse_location_and_omits_coordinates(
    api, wholesaler, farmer, farmer_product
):
    farmer.location = "Exact farm address, Kebele 04"
    farmer.latitude = "9.123456"
    farmer.longitude = "38.123456"
    farmer.save(update_fields=["location", "latitude", "longitude"])
    api.force_authenticate(user=wholesaler)

    response = api.get(
        f"/api/v1/products/farmer-listings/{farmer_product.id}/"
    )

    assert response.status_code == 200, response.data
    assert "owner_latitude" not in response.data
    assert "owner_longitude" not in response.data
    assert "Exact farm address" not in response.data["owner_location"]


def test_chat_participants_do_not_expose_contact_details(
    api, farmer, wholesaler
):
    api.force_authenticate(user=farmer)

    response = api.post(
        "/api/v1/chat/channels/",
        {"participant_ids": [str(wholesaler.pk)]},
        format="json",
    )

    assert response.status_code == 201, response.data
    participants = response.data["channel"]["participants"]
    assert all("phone" not in participant for participant in participants)
    assert all("location" not in participant for participant in participants)


def test_order_contact_details_require_explicit_staff_disclosure(
    api, farmer, wholesaler, farmer_product, financial_manager
):
    farmer.phone = "+251900000001"
    farmer.location = "Farmer exact location"
    farmer.save(update_fields=["phone", "location"])
    wholesaler.phone = "+251900000002"
    wholesaler.location = "Buyer exact location"
    wholesaler.save(update_fields=["phone", "location"])

    api.force_authenticate(user=wholesaler)
    created = api.post(
        "/api/v1/orders/",
        {
            "product": str(farmer_product.pk),
            "quantity": "2",
            "delivery_information": "Private delivery address",
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    order_id = created.data["order"]["id"]

    api.force_authenticate(user=farmer)
    before_acceptance = api.get(f"/api/v1/orders/{order_id}/")
    assert before_acceptance.status_code == 200
    assert before_acceptance.data["delivery_information"] == ""
    assert before_acceptance.data["counterparty_contact"] is None

    api.force_authenticate(user=wholesaler)
    buyer_before_acceptance = api.get(f"/api/v1/orders/{order_id}/")
    assert buyer_before_acceptance.data["delivery_information"] == (
        "Private delivery address"
    )
    assert buyer_before_acceptance.data["counterparty_contact"] is None

    api.force_authenticate(user=farmer)
    accepted = api.patch(
        f"/api/v1/orders/{order_id}/status/",
        {"status": OrderStatus.ACCEPTED},
        format="json",
    )
    assert accepted.status_code == 200, accepted.data
    assert accepted.data["order"]["counterparty_contact"] is None
    assert accepted.data["order"]["delivery_information"] == ""
    assert not AuditLog.objects.filter(
        action="order_contact_access_granted",
        detail__contains=f"order_id={order_id}",
    ).exists()

    seller_after_acceptance = api.get(f"/api/v1/orders/{order_id}/")
    assert seller_after_acceptance.data["delivery_information"] == ""
    assert seller_after_acceptance.data["counterparty_contact"] is None

    api.force_authenticate(user=wholesaler)
    buyer_after_acceptance = api.get(f"/api/v1/orders/{order_id}/")
    assert buyer_after_acceptance.data["counterparty_contact"] is None

    api.force_authenticate(user=financial_manager)
    disclose_to_seller = api.post(
        f"/api/v1/orders/{order_id}/disclose-contact/",
        {
            "recipient_id": str(farmer.pk),
            "fields": ["phone", "delivery_information"],
            "reason": "Accepted order delivery coordination",
        },
        format="json",
    )
    assert disclose_to_seller.status_code == 200, disclose_to_seller.data
    assert disclose_to_seller.data["order"]["counterparty_contact"] is None

    api.force_authenticate(user=farmer)
    seller_after_disclosure = api.get(f"/api/v1/orders/{order_id}/")
    assert seller_after_disclosure.data["delivery_information"] == (
        "Private delivery address"
    )
    assert seller_after_disclosure.data["counterparty_contact"]["phone"] == (
        wholesaler.phone
    )
    assert "email" not in seller_after_disclosure.data["counterparty_contact"]

    api.force_authenticate(user=financial_manager)
    disclose_to_buyer = api.post(
        f"/api/v1/orders/{order_id}/disclose-contact/",
        {
            "recipient_id": str(wholesaler.pk),
            "fields": ["phone"],
            "reason": "Accepted order communication",
        },
        format="json",
    )
    assert disclose_to_buyer.status_code == 200, disclose_to_buyer.data

    api.force_authenticate(user=wholesaler)
    buyer_after_disclosure = api.get(f"/api/v1/orders/{order_id}/")
    assert buyer_after_disclosure.data["counterparty_contact"]["phone"] == farmer.phone
    assert "email" not in buyer_after_disclosure.data["counterparty_contact"]

    order = Order.objects.get(pk=order_id)
    audit = AuditLog.objects.filter(action="order_contact_disclosed").order_by(
        "created_at"
    )
    assert audit.count() == 2
    assert all(item.target == order.reference for item in audit)
    assert all("reason=" in item.detail for item in audit)
    assert all(wholesaler.phone not in item.detail for item in audit)


def test_cancelled_or_refunded_order_retracts_seller_contact_access(
    api, farmer, wholesaler, farmer_product
):
    api.force_authenticate(user=wholesaler)
    created = api.post(
        "/api/v1/orders/",
        {
            "product": str(farmer_product.pk),
            "quantity": "1",
            "delivery_information": "Do not retain after cancellation",
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    order = Order.objects.get(pk=created.data["order"]["id"])
    order.status = OrderStatus.CANCELLED
    order.payment_status = OrderPaymentStatus.REFUNDED
    order.save(update_fields=["status", "payment_status"])

    api.force_authenticate(user=farmer)
    response = api.get(f"/api/v1/orders/{order.pk}/")

    assert response.status_code == 200
    assert response.data["delivery_information"] == ""
    assert response.data["counterparty_contact"] is None
