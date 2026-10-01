"""Order and payment workflow tests (UC-04, doc 5.1.5, FR-W-04, FR-FM-01..04)."""
import pytest

from notifications.models import Notification
from payments.models import Order, OrderStatus, PaymentRecord, PaymentStatus
from products.models import ProductStatus

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Order creation (FR-W-04)
# ---------------------------------------------------------------------------
def test_wholesaler_places_order_and_stock_is_reserved(api, wholesaler, farmer_product):
    api.force_authenticate(user=wholesaler)
    response = api.post(
        "/api/v1/orders/",
        {"product": str(farmer_product.id), "quantity": "50"},
        format="json",
    )
    assert response.status_code == 201, response.data
    order = Order.objects.get()
    assert order.reference.startswith("#ORD")
    assert order.total_amount == 1250  # 50 kg x 25 ETB
    assert order.status == OrderStatus.PROCESSING
    farmer_product.refresh_from_db()
    assert float(farmer_product.quantity) == 150  # 200 - 50 reserved


def test_order_reference_is_unique(api, wholesaler, farmer_product):
    for _ in range(3):
        api.force_authenticate(user=wholesaler)
        response = api.post(
            "/api/v1/orders/",
            {"product": str(farmer_product.id), "quantity": "10"},
            format="json",
        )
        assert response.status_code == 201
    assert len(set(Order.objects.values_list("reference", flat=True))) == 3


def test_order_beyond_available_stock_rejected(api, wholesaler, farmer_product):
    api.force_authenticate(user=wholesaler)
    response = api.post(
        "/api/v1/orders/",
        {"product": str(farmer_product.id), "quantity": "5000"},
        format="json",
    )
    assert response.status_code == 400
    assert Order.objects.count() == 0


def test_inactive_listing_cannot_be_ordered(api, wholesaler, farmer_product):
    farmer_product.deactivate()
    api.force_authenticate(user=wholesaler)
    response = api.post(
        "/api/v1/orders/",
        {"product": str(farmer_product.id), "quantity": "5"},
        format="json",
    )
    assert response.status_code == 400


def test_farmer_cannot_place_an_order(api, farmer, farmer_product):
    api.force_authenticate(user=farmer)
    response = api.post(
        "/api/v1/orders/",
        {"product": str(farmer_product.id), "quantity": "5"},
        format="json",
    )
    assert response.status_code == 403


def test_order_created_notifies_the_farmer(api, wholesaler, farmer, farmer_product):
    api.force_authenticate(user=wholesaler)
    api.post(
        "/api/v1/orders/",
        {"product": str(farmer_product.id), "quantity": "5"},
        format="json",
    )
    assert Notification.objects.filter(recipient=farmer, type="ORDER").exists()


# ---------------------------------------------------------------------------
# Order status workflow
# ---------------------------------------------------------------------------
def test_order_status_progression(api, wholesaler, order):
    api.force_authenticate(user=wholesaler)
    for target in ("Confirmed", "Shipped", "Delivered"):
        response = api.patch(
            f"/api/v1/orders/{order.id}/status/", {"status": target}, format="json"
        )
        assert response.status_code == 200, (target, response.data)
        order.refresh_from_db()
        assert order.status == target


def test_delivered_is_terminal(api, wholesaler, order):
    api.force_authenticate(user=wholesaler)
    for target in ("Confirmed", "Shipped", "Delivered"):
        api.patch(
            f"/api/v1/orders/{order.id}/status/", {"status": target}, format="json"
        )
    order.refresh_from_db()
    assert order.status == OrderStatus.DELIVERED
    response = api.patch(
        f"/api/v1/orders/{order.id}/status/", {"status": "Cancelled"}, format="json"
    )
    assert response.status_code == 400
    order.refresh_from_db()
    assert order.status == OrderStatus.DELIVERED


def test_illegal_status_transition_rejected(api, wholesaler, order):
    api.force_authenticate(user=wholesaler)
    response = api.patch(
        f"/api/v1/orders/{order.id}/status/", {"status": "Delivered"}, format="json"
    )
    assert response.status_code == 400
    order.refresh_from_db()
    assert order.status == OrderStatus.PROCESSING


def test_unknown_status_rejected(api, wholesaler, order):
    api.force_authenticate(user=wholesaler)
    response = api.patch(
        f"/api/v1/orders/{order.id}/status/", {"status": "Teleported"}, format="json"
    )
    assert response.status_code == 400


def test_status_transition_requires_a_value(api, wholesaler, order):
    api.force_authenticate(user=wholesaler)
    response = api.patch(f"/api/v1/orders/{order.id}/status/", {}, format="json")
    assert response.status_code == 400


def test_counterparty_farmer_can_advance_status(api, farmer, order):
    api.force_authenticate(user=farmer)
    response = api.patch(
        f"/api/v1/orders/{order.id}/status/", {"status": "Confirmed"}, format="json"
    )
    assert response.status_code == 200


def test_outsider_cannot_change_order_status(api, retailer, order):
    """Retailers have no order visibility, so the row is hidden entirely."""
    api.force_authenticate(user=retailer)
    response = api.patch(
        f"/api/v1/orders/{order.id}/status/", {"status": "Confirmed"}, format="json"
    )
    assert response.status_code == 404
    order.refresh_from_db()
    assert order.status == OrderStatus.PROCESSING


def test_cancelling_releases_reserved_stock(api, wholesaler, farmer_product):
    api.force_authenticate(user=wholesaler)
    created = api.post(
        "/api/v1/orders/",
        {"product": str(farmer_product.id), "quantity": "50"},
        format="json",
    )
    order = Order.objects.get(pk=created.data["order"]["id"])
    response = api.patch(
        f"/api/v1/orders/{order.id}/status/", {"status": "Cancelled"}, format="json"
    )
    assert response.status_code == 200
    farmer_product.refresh_from_db()
    assert float(farmer_product.quantity) == 200


def test_counterparty_sees_the_order(api, farmer, order):
    api.force_authenticate(user=farmer)
    response = api.get("/api/v1/orders/")
    assert response.status_code == 200
    assert response.data["count"] == 1


def test_outsider_cannot_see_the_order(api, retailer, order):
    api.force_authenticate(user=retailer)
    response = api.get("/api/v1/orders/")
    assert response.data["count"] == 0


# ---------------------------------------------------------------------------
# Payment list isolation (doc 3.8 / NFR-04)
# ---------------------------------------------------------------------------
def test_wholesaler_sees_only_own_payments(api, wholesaler, wholesaler_b, payment):
    api.force_authenticate(user=wholesaler)
    response = api.get("/api/v1/payments/")
    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == str(payment.id)


def test_farmer_sees_only_own_incoming_payments(api, wholesaler, farmer, farmer_b, payment):
    api.force_authenticate(user=farmer)
    assert api.get("/api/v1/payments/").data["count"] == 1
    api.force_authenticate(user=farmer_b)
    assert api.get("/api/v1/payments/").data["count"] == 0


def test_retailer_sees_no_payments(api, retailer, payment):
    api.force_authenticate(user=retailer)
    assert api.get("/api/v1/payments/").data["count"] == 0


def test_financial_manager_sees_every_payment(api, financial_manager, payment):
    api.force_authenticate(user=financial_manager)
    assert api.get("/api/v1/payments/").data["count"] == 1


def test_payment_search_and_status_filter(api, financial_manager, payment):
    payment.status = PaymentStatus.FLAGGED
    payment.save()
    api.force_authenticate(user=financial_manager)
    assert api.get("/api/v1/payments/", {"status": "FLAGGED"}).data["count"] == 1
    assert api.get("/api/v1/payments/", {"search": "CBE-1"}).data["count"] == 1
    assert api.get("/api/v1/payments/", {"search": "nothing"}).data["count"] == 0


# ---------------------------------------------------------------------------
# Payment decision workflow
# ---------------------------------------------------------------------------
def test_verify_records_the_financial_manager(api, financial_manager, payment):
    api.force_authenticate(user=financial_manager)
    response = api.patch(
        f"/api/v1/payments/{payment.id}/verify/",
        {"notes": "Confirmed with bank statement"},
        format="json",
    )
    assert response.status_code == 200
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.VERIFIED
    assert payment.verified_by == financial_manager
    assert payment.notes == "Confirmed with bank statement"


def test_flag_records_the_reason(api, financial_manager, payment):
    api.force_authenticate(user=financial_manager)
    response = api.patch(
        f"/api/v1/payments/{payment.id}/flag/",
        {"reason": "Amount mismatch"},
        format="json",
    )
    assert response.status_code == 200
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.FLAGGED
    assert "Amount mismatch" in payment.notes
    assert Notification.objects.filter(recipient=payment.submitted_by).exists()


def test_dispute_requires_a_flagged_payment(api, financial_manager, payment):
    api.force_authenticate(user=financial_manager)
    response = api.patch(
        f"/api/v1/payments/{payment.id}/dispute/",
        {"reason": "Farmer disputes receipt"},
        format="json",
    )
    assert response.status_code == 400
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.PENDING


def test_flag_then_dispute(api, financial_manager, payment):
    api.force_authenticate(user=financial_manager)
    api.patch(
        f"/api/v1/payments/{payment.id}/flag/", {"reason": "Amount mismatch"}, format="json"
    )
    response = api.patch(
        f"/api/v1/payments/{payment.id}/dispute/",
        {"reason": "Farmer disputes receipt"},
        format="json",
    )
    assert response.status_code == 200
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.DISPUTED
    assert payment.notes == "Farmer disputes receipt"


def test_verified_payment_cannot_be_verified_twice(api, financial_manager, payment):
    payment.verify(financial_manager)
    api.force_authenticate(user=financial_manager)
    response = api.patch(f"/api/v1/payments/{payment.id}/verify/", {}, format="json")
    assert response.status_code == 400
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.VERIFIED


def test_only_financial_manager_makes_decisions(api, user_admin, payment):
    api.force_authenticate(user=user_admin)
    assert api.patch(f"/api/v1/payments/{payment.id}/verify/").status_code == 403
    assert api.patch(f"/api/v1/payments/{payment.id}/flag/").status_code == 403


def test_receipt_payload(api, financial_manager, payment):
    payment.verify(financial_manager)
    api.force_authenticate(user=financial_manager)
    response = api.get(f"/api/v1/payments/{payment.id}/receipt/")
    assert response.status_code == 200
    receipt = response.data["receipt"]
    assert receipt["receipt_id"] == payment.display_id
    assert receipt["amount"] == "1250.00"
    assert receipt["status"] == "VERIFIED"
    assert receipt["verified_by"] == financial_manager.full_name
    assert receipt["currency"] == "ETB"


# ---------------------------------------------------------------------------
# Payment validation
# ---------------------------------------------------------------------------
def test_cannot_pay_for_another_wholesaler(api, wholesaler, wholesaler_b, farmer, farmer_product):
    api.force_authenticate(user=wholesaler_b)
    response = api.post(
        "/api/v1/payments/",
        {
            "submitted_by": str(wholesaler.id),
            "farmer": str(farmer.id),
            "product": str(farmer_product.id),
            "amount": "100",
            "payment_method": "CBE Birr",
        },
        format="json",
    )
    assert response.status_code == 400


def test_product_must_belong_to_the_selected_farmer(api, wholesaler, farmer_b, farmer_product):
    api.force_authenticate(user=wholesaler)
    response = api.post(
        "/api/v1/payments/",
        {
            "submitted_by": str(wholesaler.id),
            "farmer": str(farmer_b.id),
            "product": str(farmer_product.id),
            "amount": "100",
            "payment_method": "CBE Birr",
        },
        format="json",
    )
    assert response.status_code == 400


def test_negative_amount_rejected(api, wholesaler, farmer, farmer_product):
    api.force_authenticate(user=wholesaler)
    response = api.post(
        "/api/v1/payments/",
        {
            "submitted_by": str(wholesaler.id),
            "farmer": str(farmer.id),
            "product": str(farmer_product.id),
            "amount": "-5",
            "payment_method": "CBE Birr",
        },
        format="json",
    )
    assert response.status_code == 400


def test_mark_sold_sets_quantity_to_zero(payment, farmer_product):
    farmer_product.mark_sold()
    farmer_product.refresh_from_db()
    assert farmer_product.status == ProductStatus.SOLD
    assert float(farmer_product.quantity) == 0


def test_soft_deleted_listing_keeps_payment_history(api, farmer, farmer_product, payment):
    farmer_product.mark_deleted()
    farmer_product.refresh_from_db()
    api.force_authenticate(user=farmer)
    response = api.get(f"/api/v1/payments/{payment.id}/")
    assert response.status_code == 200
    assert PaymentRecord.objects.filter(pk=payment.id).exists()
