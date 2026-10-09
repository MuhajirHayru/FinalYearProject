"""Event-driven control flow (doc 4.11.2).

Domain events fire through Django signals and are the single trigger for
notification generation.  Views therefore never import ``notify`` directly for
these events, which keeps the workflows declarative and makes the event stream
easy to extend (e.g. adding an SMS gateway later) without touching business
logic.

Event catalogue:

============================  ==========================================
``user_registered``           A new PENDING account entered the queue.
``user_approved``             A User Admin approved a registration.
``user_rejected``             A User Admin rejected a registration.
``payment_submitted``         A wholesaler submitted a payment record.
``payment_verified``          A Financial Manager verified a payment.
``payment_flagged``           A Financial Manager flagged a discrepancy.
``order_created``             A wholesaler placed a procurement order.
``message_received``          A chat message was persisted.
============================  ==========================================
"""
from chat.models import Message
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from notifications.services import notify
from payments.models import Order, OrderStatus, PaymentRecord, PaymentStatus
from users.models import AccountStatus, User


@receiver(post_save, sender=User)
def user_registered(sender, instance, created, **kwargs):
    """Notify the approval queue (UC-01 step 7)."""
    if not created or instance.role not in ("FARMER", "WHOLESALER", "RETAILER"):
        return
    notify(
        roles=("USER_ADMIN", "SUPER_ADMIN"),
        type="REGISTRATION",
        message=(
            f"New {instance.get_role_display().lower()} registration pending "
            f"approval: {instance.full_name}"
        ),
        actor=instance,
    )


@receiver(post_save, sender=User)
def user_status_changed(sender, instance, created, update_fields=None, **kwargs):
    """Mirror approval/rejection decisions to the affected user."""
    if created or not update_fields or "status" not in update_fields:
        return
    if instance.status == AccountStatus.APPROVED:
        notify(
            user_ids=[instance.id],
            type="APPROVAL",
            message="Your account has been approved. You can now log in.",
            actor=None,
        )
    elif instance.status == AccountStatus.REJECTED:
        reason = f" Reason: {instance.rejection_reason}" if instance.rejection_reason else ""
        notify(
            user_ids=[instance.id],
            type="REJECTION",
            message=f"Your registration was rejected.{reason}",
            actor=None,
        )
    elif instance.status == AccountStatus.SUSPENDED:
        notify(
            user_ids=[instance.id],
            type="SYSTEM",
            message="Your account has been suspended by an administrator.",
            actor=None,
        )


@receiver(post_save, sender=PaymentRecord)
def payment_submitted(sender, instance, created, **kwargs):
    """Financial Manager queue notification (UC-04 step 6)."""
    if not created:
        return
    notify(
        roles=("FINANCIAL_MANAGER", "SUPER_ADMIN"),
        type="PAYMENT",
        message=(
            f"New payment of {instance.amount} ETB submitted by "
            f"{instance.submitted_by.full_name} for {instance.product.title}"
        ),
        actor=instance.submitted_by,
    )


@receiver(post_save, sender=PaymentRecord)
def payment_status_changed(sender, instance, created, **kwargs):
    """Confirmations to both parties once a decision is recorded."""
    if created or instance.status == PaymentStatus.PENDING:
        return
    if instance.status == PaymentStatus.VERIFIED:
        notify(
            user_ids=[instance.submitted_by_id, instance.farmer_id],
            type="PAYMENT",
            message=(
                f"Payment {instance.display_id} of {instance.amount} ETB "
                "has been verified."
            ),
            actor=instance.verified_by,
        )
    elif instance.status == PaymentStatus.FLAGGED:
        reason = f" Reason: {instance.notes}" if instance.notes else ""
        notify(
            user_ids=[instance.submitted_by_id],
            type="PAYMENT",
            message=f"Payment {instance.display_id} flagged for review.{reason}",
            actor=instance.verified_by,
        )
    elif instance.status == PaymentStatus.DISPUTED:
        notify(
            user_ids=[instance.submitted_by_id, instance.farmer_id],
            type="PAYMENT",
            message=(
                f"Payment {instance.display_id} has been marked as disputed. "
                "Please contact the Financial Manager."
            ),
            actor=instance.verified_by,
        )


@receiver(post_save, sender=Order)
def order_created(sender, instance, created, **kwargs):
    if created:
        seller = instance.seller
        buyer = instance.buyer
        notify(
            user_ids=[seller.id],
            type="ORDER",
            message=(
                f"New order {instance.reference} for {instance.quantity} "
                f"{instance.product.unit_of_measure} of "
                f'"{instance.product.title}" from {buyer.full_name}'
            ),
            actor=buyer,
            target_url=f"/orders/{instance.id}",
        )
        return
    if not hasattr(instance, "_previous_status"):
        return
    previous = instance._previous_status
    if previous == instance.status:
        return
    messages = {
        OrderStatus.ACCEPTED: "The seller accepted your order and activated its agreement.",
        OrderStatus.REJECTED: "The seller rejected your order. Reserved funds were returned.",
        OrderStatus.SHIPPED: "Your order has been dispatched.",
        OrderStatus.AWAITING_QUALITY_CONFIRMATION: (
            "Your delivery arrived. Confirm quality or report a dispute."
        ),
        OrderStatus.AWAITING_PAYMENT_RELEASE: (
            "Quality was confirmed. The Financial Manager will review escrow release."
        ),
        OrderStatus.COMPLETED: "The order is complete and escrow has been released.",
        OrderStatus.DISPUTED: "A quality dispute is open; escrow is on hold.",
        OrderStatus.CANCELLED: "The order was cancelled and reserved funds returned.",
    }
    message = messages.get(instance.status)
    if message:
        notify(
            user_ids=[instance.buyer.id, instance.seller.id],
            type="ORDER",
            message=f"Order {instance.reference}: {message}",
            actor=None,
            target_url=f"/orders/{instance.id}",
        )


@receiver(pre_save, sender=Order)
def remember_order_status(sender, instance, **kwargs):
    if not instance._state.adding:
        instance._previous_status = (
            Order.objects.filter(pk=instance.pk)
            .values_list("status", flat=True)
            .first()
        )


@receiver(post_save, sender=Message)
def message_received(sender, instance, created, **kwargs):
    """Alert every other participant that a new message arrived (UC-03)."""
    if not created:
        return
    recipient_ids = [
        pk
        for pk in instance.channel.participants.values_list("id", flat=True)
        if pk != instance.sender_id
    ]
    if not recipient_ids:
        return
    topic = (
        f' about "{instance.channel.related_product.title}"'
        if instance.channel.related_product_id
        else ""
    )
    notify(
        user_ids=recipient_ids,
        type="MESSAGE",
        message=f"New message from {instance.sender.full_name}{topic}",
        actor=instance.sender,
    )
