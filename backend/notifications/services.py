"""Event-driven notification generation and delivery (doc 4.3 / 4.11.2).

``notify`` is the single entry point used by every domain workflow.  It
persists an in-app notification *and* pushes it to the recipient's WebSocket
group so alerts arrive without polling.
"""
import logging

from greenpath.realtime import push_notification_event

from .models import Notification

logger = logging.getLogger(__name__)


def _resolve_recipients(user_ids=None, roles=None, exclude=None):
    from users.models import AccountStatus, User

    qs = User.objects.none()
    if user_ids:
        qs = User.objects.filter(id__in=list(user_ids))
    elif roles:
        qs = User.objects.filter(role__in=list(roles), status=AccountStatus.APPROVED)
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return list(qs)


def notify(
    user_ids=None,
    roles=None,
    type="SYSTEM",
    message="",
    actor=None,
    target_url="",
):
    """Create in-app notifications for specific users or roles.

    Returns the list of created ``Notification`` rows.
    """
    recipients = _resolve_recipients(user_ids=user_ids, roles=roles)
    if not recipients:
        return []

    created = list(
        Notification.objects.bulk_create(
            [
                Notification(
                    recipient=u,
                    type=type,
                    message=message,
                    actor=actor,
                    target_url=target_url,
                )
                for u in recipients
            ]
        )
    )
    for notification in created:
        # Envelope type identifies the socket event; the notification's own
        # category is nested under "notification" so the two cannot collide.
        push_notification_event(
            notification.recipient_id,
            {
                "type": "notify.event",
                "notification": _payload(notification),
            },
        )
    return created


def _payload(notification):
    return {
        "id": str(notification.id),
        "type": notification.type,
        "type_display": notification.get_type_display(),
        "message": notification.message,
        "target_url": notification.target_url,
        "is_read": notification.is_read,
        "created_at": notification.created_at.isoformat(),
    }
