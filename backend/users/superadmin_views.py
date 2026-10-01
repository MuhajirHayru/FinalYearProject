"""Super Admin module (doc 3.3.1.6 — FR-SA-01 .. FR-SA-05).

Grants platform-wide governance:

* FR-SA-01 — unrestricted read access to every module's data.
* FR-SA-02 — create, modify and deactivate Admin sub-role accounts.
* FR-SA-03 — override or reverse a User Admin approval/suspension decision.
* FR-SA-04 — configure system parameters and the platform announcement.
* FR-SA-05 — system health metrics (users, transactions, API performance).
"""
from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema

from chat.models import ChatChannel, Message
from notifications.models import Notification
from payments.models import Order, PaymentRecord, PaymentStatus
from products.models import Product, ProductStatus, ProductType
from users.permissions import IsSuperAdmin

from .models import AccountStatus, AuditLog, PlatformSettings, Role, User
from .serializers import (
    AdminAccountSerializer,
    AnnouncementSerializer,
    AuditLogSerializer,
    DirectoryUserSerializer,
    PlatformSettingsUpdateSerializer,
    SuperAdminDecisionSerializer,
)

ADMIN_SUBROLES = (Role.USER_ADMIN, Role.FINANCIAL_MANAGER)


class _AuditMixin:
    def _audit(self, action, target, extra=""):
        from .models import AuditLog

        AuditLog.objects.create(
            actor=self.request.user,
            action=action,
            target=str(target),
            detail=extra,
        )


# ---------------------------------------------------------------------------
# FR-SA-02 — Admin account management
# ---------------------------------------------------------------------------
class AdminAccountViewSet(_AuditMixin, viewsets.ModelViewSet):
    """CRUD over User Admin / Financial Manager accounts.

    ``/api/v1/superadmin/accounts/``
    """

    permission_classes = [IsSuperAdmin]
    serializer_class = AdminAccountSerializer
    queryset = User.objects.filter(role__in=ADMIN_SUBROLES).order_by("-created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        status_param = self.request.query_params.get("status")
        if status_param and status_param != "ALL":
            qs = qs.filter(status=status_param)
        search = (self.request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(Q(full_name__icontains=search) | Q(email__icontains=search))
        return qs

    def perform_create(self, serializer):
        user = serializer.save()
        self._audit("admin_account_created", user.email)
        from notifications.services import notify

        notify(
            user_ids=[user.id],
            type="SYSTEM",
            message="An administrator has created your admin account.",
            actor=self.request.user,
        )

    def perform_update(self, serializer):
        user = serializer.save()
        self._audit("admin_account_updated", user.email)

    def perform_destroy(self, instance):
        if instance == self.request.user:
            from rest_framework.exceptions import ValidationError

            raise ValidationError("You cannot delete your own account.")
        email = instance.email
        instance.deactivate(actor=self.request.user)
        self._audit("admin_account_deactivated", email)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        """POST /api/v1/superadmin/accounts/{id}/deactivate/ — soft-ban."""
        user = self.get_object()
        if user == request.user:
            return Response(
                {"success": False, "error": "You cannot deactivate your own account."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.deactivate(actor=request.user)
        self._audit("admin_account_deactivated", user.email)
        return Response(
            {
                "success": True,
                "message": f"{user.full_name} deactivated.",
                "user": DirectoryUserSerializer(user).data,
            }
        )

    @action(detail=True, methods=["post"])
    def reinstate(self, request, pk=None):
        """POST /api/v1/superadmin/accounts/{id}/reinstate/ — undo a deactivation."""
        user = self.get_object()
        user.status = AccountStatus.APPROVED
        user.is_active = True
        user.save(update_fields=["status", "is_active", "updated_at"])
        self._audit("admin_account_reinstated", user.email)
        return Response(
            {
                "success": True,
                "message": f"{user.full_name} reinstated.",
                "user": DirectoryUserSerializer(user).data,
            }
        )


# ---------------------------------------------------------------------------
# FR-SA-03 — override / reverse User Admin decisions
# ---------------------------------------------------------------------------
@extend_schema(
    request=SuperAdminDecisionSerializer, responses=OpenApiTypes.OBJECT
)
class OverrideDecisionView(APIView):
    """POST /api/v1/superadmin/users/{id}/override/ — reverse an admin decision.

    Accepts ``{"decision": "APPROVE" | "REJECT" | "SUSPEND" | "REACTIVATE"}``
    with an optional ``reason``.
    """

    permission_classes = [IsSuperAdmin]
    DECISIONS = ("APPROVE", "REJECT", "SUSPEND", "REACTIVATE")

    def post(self, request, pk):
        user = User.objects.filter(pk=pk).first()
        if user is None:
            return Response({"success": False, "error": "User not found."}, status=404)

        decision = (request.data.get("decision") or "").upper()
        if decision not in self.DECISIONS:
            return Response(
                {
                    "success": False,
                    "error": f"decision must be one of {', '.join(self.DECISIONS)}.",
                },
                status=400,
            )
        if user == request.user:
            return Response(
                {"success": False, "error": "You cannot override your own account."},
                status=400,
            )

        reason = (request.data.get("reason") or "").strip()
        previous = user.status

        if decision == "APPROVE":
            user.approve(actor=request.user)
        elif decision == "REJECT":
            user.reject(reason, actor=request.user)
        elif decision == "SUSPEND":
            user.suspend(actor=request.user)
        else:
            user.reinstate(actor=request.user)

        from .models import AuditLog

        AuditLog.objects.create(
            actor=request.user,
            action="user_decision_overridden",
            target=user.email,
            detail=f"{previous} -> {user.status}. {reason}".strip(),
        )

        from notifications.services import notify

        notify(
            user_ids=[user.id],
            type="APPROVAL" if user.status == AccountStatus.APPROVED else "SYSTEM",
            message=(
                f"Your account status was updated to "
                f"{user.get_status_display().lower()} by the Super Admin."
                f"{' Reason: ' + reason if reason else ''}"
            ),
            actor=request.user,
        )
        return Response(
            {
                "success": True,
                "message": f"{user.full_name}: {previous} -> {user.status}",
                "previous_status": previous,
                "user": DirectoryUserSerializer(user).data,
            }
        )


# ---------------------------------------------------------------------------
# FR-SA-01 — unrestricted read access across modules
# ---------------------------------------------------------------------------
@extend_schema(responses=OpenApiTypes.OBJECT)
class SuperAdminDataView(APIView):
    """GET /api/v1/superadmin/data/?resource=users|products|orders|payments|chat."""

    permission_classes = [IsSuperAdmin]
    RESOURCES = ("users", "products", "orders", "payments", "chat", "notifications")

    def get(self, request):
        resource = (request.query_params.get("resource") or "users").lower()
        if resource not in self.RESOURCES:
            return Response(
                {
                    "success": False,
                    "error": (
                        f"Unknown resource. Valid values: {', '.join(self.RESOURCES)}."
                    ),
                },
                status=400,
            )

        limit = min(int(request.query_params.get("limit", 50)), 200)
        handler = getattr(self, f"_{resource}")
        rows = handler(limit)
        return Response({"success": True, "resource": resource, "count": len(rows), "results": rows})

    @staticmethod
    def _user_row(u):
        return {
            "id": str(u.id),
            "full_name": u.full_name,
            "email": u.email,
            "role": u.role,
            "status": u.status,
            "location": u.location,
            "created_at": u.created_at.isoformat(),
        }

    def _users(self, limit):
        return [self._user_row(u) for u in User.objects.all()[:limit]]

    def _products(self, limit):
        return [
            {
                "id": str(p.id),
                "title": p.title,
                "owner": p.owner.full_name,
                "product_type": p.product_type,
                "category": p.category,
                "quantity": str(p.quantity),
                "price_per_unit": str(p.price_per_unit),
                "status": p.status,
            }
            for p in Product.objects.select_related("owner")[:limit]
        ]

    def _orders(self, limit):
        return [
            {
                "id": str(o.id),
                "reference": o.reference,
                "wholesaler": o.wholesaler.full_name,
                "farmer": o.farmer.full_name,
                "product": o.product.title,
                "total_amount": str(o.total_amount),
                "status": o.status,
                "created_at": o.created_at.isoformat(),
            }
            for o in Order.objects.select_related("wholesaler", "farmer", "product")[:limit]
        ]

    def _payments(self, limit):
        return [
            {
                "id": str(p.id),
                "display_id": p.display_id,
                "wholesaler": p.submitted_by.full_name,
                "farmer": p.farmer.full_name,
                "amount": str(p.amount),
                "payment_method": p.payment_method,
                "status": p.status,
                "submitted_at": p.submitted_at.isoformat(),
            }
            for p in PaymentRecord.objects.select_related(
                "submitted_by", "farmer"
            )[:limit]
        ]

    def _chat(self, limit):
        return [
            {
                "id": str(c.id),
                "participants": [p.full_name for p in c.participants.all()],
                "message_count": c.messages.count(),
                "last_message_at": c.last_message_at.isoformat() if c.last_message_at else None,
            }
            for c in ChatChannel.objects.prefetch_related("participants")[:limit]
        ]

    def _notifications(self, limit):
        return [
            {
                "id": str(n.id),
                "recipient": n.recipient.full_name,
                "type": n.type,
                "message": n.message,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat(),
            }
            for n in Notification.objects.select_related("recipient")[:limit]
        ]


# ---------------------------------------------------------------------------
# FR-SA-04 — system-wide configuration
# ---------------------------------------------------------------------------
@extend_schema(
    request=PlatformSettingsUpdateSerializer, responses=OpenApiTypes.OBJECT
)
class PlatformSettingsView(APIView):
    """GET/PATCH /api/v1/superadmin/settings/"""

    permission_classes = [IsSuperAdmin]
    FIELDS = (
        "registration_open",
        "require_approval",
        "announcement",
        "maintenance_mode",
    )

    def get(self, request):
        config = PlatformSettings.load()
        return Response({"success": True, "settings": self._serialize(config)})

    def patch(self, request):
        config = PlatformSettings.load()
        changed = {}
        for field in self.FIELDS:
            if field in request.data:
                setattr(config, field, request.data[field])
                changed[field] = getattr(config, field)
        if not changed:
            return Response(
                {
                    "success": False,
                    "error": f"No settings supplied. Valid fields: {', '.join(self.FIELDS)}.",
                },
                status=400,
            )
        config.updated_by = request.user
        config.save()

        from .models import AuditLog

        AuditLog.objects.create(
            actor=request.user,
            action="platform_settings_updated",
            target="platform",
            detail=", ".join(f"{k}={v}" for k, v in changed.items()),
        )

        if config.announcement:
            from notifications.services import notify

            notify(
                roles=tuple(Role.values),
                type="SYSTEM",
                message=config.announcement,
                actor=request.user,
            )

        return Response(
            {"success": True, "updated": changed, "settings": self._serialize(config)}
        )

    @staticmethod
    def _serialize(config):
        return {
            "registration_open": config.registration_open,
            "require_approval": config.require_approval,
            "announcement": config.announcement,
            "maintenance_mode": config.maintenance_mode,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None,
            "updated_by": config.updated_by.full_name if config.updated_by else None,
        }


@extend_schema(
    request=AnnouncementSerializer, responses=OpenApiTypes.OBJECT
)
class AnnouncementBroadcastView(APIView):
    """POST /api/v1/superadmin/announcement/ — push an announcement to everyone."""

    permission_classes = [IsSuperAdmin]

    def post(self, request):
        message = (request.data.get("message") or "").strip()
        if not message:
            return Response(
                {"success": False, "error": "Announcement text is required."}, status=400
            )
        config = PlatformSettings.load()
        config.announcement = message
        config.updated_by = request.user
        config.save(update_fields=["announcement", "updated_by", "updated_at"])

        from notifications.services import notify

        created = notify(
            roles=tuple(Role.values), type="SYSTEM", message=message, actor=request.user
        )
        return Response(
            {
                "success": True,
                "message": f"Announcement delivered to {len(created)} user(s).",
                "recipients": len(created),
            },
            status=201,
        )


# ---------------------------------------------------------------------------
# FR-SA-05 — system health metrics
# ---------------------------------------------------------------------------
@extend_schema(responses=OpenApiTypes.OBJECT)
class SystemHealthView(APIView):
    """GET /api/v1/superadmin/health/ — users, volumes and performance counters."""

    permission_classes = [IsSuperAdmin]

    def get(self, request):
        now = timezone.now()
        day_ago = now - timezone.timedelta(days=1)
        week_ago = now - timezone.timedelta(days=7)

        verified = PaymentRecord.objects.filter(status=PaymentStatus.VERIFIED)
        pending = PaymentRecord.objects.filter(status=PaymentStatus.PENDING)

        by_role = {
            row["role"]: row["c"]
            for row in User.objects.values("role").annotate(c=Count("id"))
        }
        by_listing_type = {
            row["product_type"]: row["c"]
            for row in Product.objects.values("product_type").annotate(c=Count("id"))
        }

        return Response(
            {
                "success": True,
                "generated_at": now,
                "users": {
                    "total": User.objects.count(),
                    "approved": User.objects.filter(status=AccountStatus.APPROVED).count(),
                    "pending": User.objects.filter(status=AccountStatus.PENDING).count(),
                    "suspended": User.objects.filter(status=AccountStatus.SUSPENDED).count(),
                    "by_role": by_role,
                },
                "listings": {
                    "total": Product.objects.count(),
                    "active": Product.objects.filter(status=ProductStatus.ACTIVE).count(),
                    "by_type": by_listing_type,
                },
                "transactions": {
                    "orders_total": Order.objects.count(),
                    "orders_24h": Order.objects.filter(created_at__gte=day_ago).count(),
                    "order_value_total": str(
                        Order.objects.aggregate(t=Sum("total_amount"))["t"] or 0
                    ),
                    "payments_total": PaymentRecord.objects.count(),
                    "payments_pending": pending.count(),
                    "payments_pending_value": str(pending.aggregate(t=Sum("amount"))["t"] or 0),
                    "payments_verified": verified.count(),
                    "payments_verified_value": str(verified.aggregate(t=Sum("amount"))["t"] or 0),
                    "payment_volume_7d": str(
                        PaymentRecord.objects.filter(submitted_at__gte=week_ago).aggregate(
                            t=Sum("amount")
                        )["t"]
                        or 0
                    ),
                },
                "communication": {
                    "chat_channels": ChatChannel.objects.count(),
                    "messages": Message.objects.count(),
                    "notifications": Notification.objects.count(),
                    "unread_notifications": Notification.objects.filter(is_read=False).count(),
                },
                "api": {
                    "version": "1.0.0",
                    "authentication": "JWT (HS256)",
                    "token_lifetime": "access 1h / refresh 7d",
                    "page_size": 20,
                    "websocket_paths": ["/ws/chat/{channel_id}/", "/ws/notifications/"],
                },
            }
        )


class AuditLogListView(mixins.ListModelMixin, viewsets.GenericViewSet):
    """GET /api/v1/superadmin/audit/ — Super Admin decision trail (FR-SA-03)."""

    permission_classes = [IsSuperAdmin]
    serializer_class = AuditLogSerializer
    queryset = AuditLog.objects.select_related("actor").order_by("-created_at")
