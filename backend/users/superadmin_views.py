"""Super Admin module (doc 3.3.1.6 — FR-SA-01 .. FR-SA-05).

Grants platform-wide governance:

* FR-SA-01 — unrestricted read access to every module's data.
* FR-SA-02 — create, modify and deactivate Admin sub-role accounts.
* FR-SA-03 — override or reverse a User Admin approval/suspension decision.
* FR-SA-04 — configure system parameters and the platform announcement.
* FR-SA-05 — system health metrics (users, transactions, API performance).
"""
from datetime import timedelta
import json

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils.dateparse import parse_date
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema

from chat.models import ChatChannel, Message
from notifications.models import Notification
from payments.models import Order, PaymentRecord, PaymentStatus
from products.models import Product, ProductStatus, ProductType
from users.permissions import IsSuperAdmin, IsUserAdmin

from .models import AccountStatus, AuditLog, PlatformSettings, Role, User
from .serializers import (
    AdminAccountSerializer,
    AnnouncementSerializer,
    AuditLogSerializer,
    DirectoryUserSerializer,
    LoginUnlockSerializer,
    PlatformSettingsUpdateSerializer,
    SuperAdminDecisionSerializer,
)
from registrations.models import (
    AdministratorScope,
    AdministrativeLocation,
    RegistrationDocument,
    RegistrationStatus,
    UserRegistration,
)
from registrations.services import (
    ADMIN_SCOPE_TYPES,
    allowed_staff_scope_types,
    administrator_scope_for,
    admin_scope_type_for_location,
    location_descendant_ids,
    manageable_admins_for,
    users_visible_to_admin,
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

    permission_classes = [IsUserAdmin]
    serializer_class = AdminAccountSerializer
    queryset = User.objects.filter(role__in=ADMIN_SUBROLES).order_by("-created_at")

    def get_queryset(self):
        qs = manageable_admins_for(
            self.request.user,
            super().get_queryset().select_related("administrative_scope__location"),
        )
        status_param = self.request.query_params.get("status")
        if status_param and status_param != "ALL":
            if status_param not in AccountStatus.values:
                raise ValidationError({"status": "Choose a valid account status."})
            qs = qs.filter(status=status_param)
        role_param = self.request.query_params.get("role")
        if role_param:
            if role_param not in ADMIN_SUBROLES:
                raise ValidationError({"role": "Choose USER_ADMIN or FINANCIAL_MANAGER."})
            qs = qs.filter(role=role_param)
        scope_type = self.request.query_params.get("scope_type")
        if scope_type:
            valid_scope_types = {"TOP_LEVEL", "FINANCIAL_MANAGER", *ADMIN_SCOPE_TYPES}
            if scope_type not in valid_scope_types:
                raise ValidationError({"scope_type": "Choose a valid administrator type."})
            if scope_type == "TOP_LEVEL":
                qs = qs.filter(
                    administrative_scope__level=AdministratorScope.Level.GLOBAL
                )
            elif scope_type == "FINANCIAL_MANAGER":
                qs = qs.filter(role=Role.FINANCIAL_MANAGER)
            else:
                scope_levels = ADMIN_SCOPE_TYPES.get(scope_type)
                if scope_levels is None:
                    raise ValidationError({"scope_type": "This administrator type is not supported."})
                qs = qs.filter(
                    role=Role.USER_ADMIN,
                    administrative_scope__level=AdministratorScope.Level.LOCATION,
                    administrative_scope__location__level__in=scope_levels,
                )

        location_id = self.request.query_params.get("location_id")
        if location_id:
            location = AdministrativeLocation.objects.filter(
                pk=location_id,
                active=True,
            ).first()
            if location is None:
                raise ValidationError({"location_id": "Choose an active location."})
            qs = qs.filter(
                administrative_scope__location_id__in=location_descendant_ids(location)
            )

        parsed_dates = {}
        for parameter, lookup in (
            ("created_from", "created_at__date__gte"),
            ("created_to", "created_at__date__lte"),
            ("last_active_from", "last_login__date__gte"),
            ("last_active_to", "last_login__date__lte"),
        ):
            raw = self.request.query_params.get(parameter)
            if raw:
                parsed = parse_date(raw)
                if parsed is None:
                    raise ValidationError({parameter: "Use an ISO date (YYYY-MM-DD)."})
                parsed_dates[parameter] = parsed
                qs = qs.filter(**{lookup: parsed})
        for start, end in (
            ("created_from", "created_to"),
            ("last_active_from", "last_active_to"),
        ):
            if start in parsed_dates and end in parsed_dates:
                if parsed_dates[start] > parsed_dates[end]:
                    raise ValidationError({start: "The start date must not be after the end date."})
        search = (self.request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(full_name__icontains=search)
                | Q(email__icontains=search)
                | Q(phone__icontains=search)
            )
        return qs.distinct().order_by("-created_at")

    @action(detail=False, methods=["get"], url_path="creation-options")
    def creation_options(self, request):
        scope = administrator_scope_for(request.user)
        return Response(
            {
                "scope_types": allowed_staff_scope_types(request.user),
                "can_create_top_level": request.user.role == Role.SUPER_ADMIN,
                "can_create_financial_manager": request.user.role == Role.SUPER_ADMIN,
                "scope_location_id": (
                    str(scope.location_id)
                    if scope and scope.location_id
                    else None
                ),
                "current_scope": (
                    "Nationwide"
                    if request.user.role == Role.SUPER_ADMIN
                    or (scope and scope.level == AdministratorScope.Level.GLOBAL)
                    else str(scope.location)
                    if scope and scope.location_id
                    else ""
                ),
            }
        )

    @action(detail=True, methods=["get"], url_path="activity")
    def activity(self, request, pk=None):
        staff = self.get_object()
        start_raw = request.query_params.get("from")
        end_raw = request.query_params.get("to")
        days_raw = request.query_params.get("days", "30")
        if start_raw:
            start_date = parse_date(start_raw)
            if start_date is None:
                raise ValidationError({"from": "Use an ISO date (YYYY-MM-DD)."})
        else:
            try:
                days = int(days_raw)
            except (TypeError, ValueError) as exc:
                raise ValidationError({"days": "Choose 7, 30, or 90."}) from exc
            if days not in (7, 30, 90):
                raise ValidationError({"days": "Choose 7, 30, or 90."})
            start_date = timezone.localdate() - timedelta(days=days - 1)
        if end_raw:
            end_date = parse_date(end_raw)
            if end_date is None:
                raise ValidationError({"to": "Use an ISO date (YYYY-MM-DD)."})
        else:
            end_date = timezone.localdate()
        if start_date > end_date:
            raise ValidationError({"from": "The start date must not be after the end date."})

        actions = AuditLog.objects.filter(
            actor=staff,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        )
        visible_users = users_visible_to_admin(staff, User.objects.all())
        role_scope = administrator_scope_for(staff)
        scope = (
            "Nationwide"
            if role_scope and role_scope.level == AdministratorScope.Level.GLOBAL
            else str(role_scope.location)
            if role_scope and role_scope.location_id
            else ""
        )
        current_users = visible_users.aggregate(
            total=Count("id"),
            farmers=Count("id", filter=Q(role=Role.FARMER)),
            wholesalers=Count("id", filter=Q(role=Role.WHOLESALER)),
            retailers=Count("id", filter=Q(role=Role.RETAILER)),
            pending=Count("id", filter=Q(status=AccountStatus.PENDING)),
        )
        created_by_event = AuditLog.objects.filter(
            action="admin_account_created",
            target__iexact=staff.email,
        ).select_related("actor").order_by("created_at").first()
        events = AuditLog.objects.filter(actor=staff).select_related(
            "actor"
        ).order_by("-created_at")
        page = self.paginate_queryset(events)
        event_rows = AuditLogSerializer(page, many=True).data
        paginated = self.get_paginated_response(event_rows).data

        return Response(
            {
                "staff": {
                    **AdminAccountSerializer(staff, context=self.get_serializer_context()).data,
                    "last_login": staff.last_login,
                    "scope": scope,
                    "permissions": staff.get_role_permissions(),
                    "created_by": (
                        {
                            "id": str(created_by_event.actor_id),
                            "name": created_by_event.actor.full_name,
                            "email": created_by_event.actor.email,
                        }
                        if created_by_event and created_by_event.actor_id
                        else None
                    ),
                },
                "period": {"from": start_date, "to": end_date},
                "statistics": {
                    "actions": actions.count(),
                    "approved": actions.filter(action="user_approved").count(),
                    "rejected": actions.filter(action="user_rejected").count(),
                    "suspended": actions.filter(action="user_suspended").count(),
                    "reactivated": actions.filter(action="user_reinstated").count(),
                    "staff_created": actions.filter(
                        action="admin_account_created"
                    ).count(),
                    "current_scope_users": current_users["total"],
                    "current_scope_farmers": current_users["farmers"],
                    "current_scope_wholesalers": current_users["wholesalers"],
                    "current_scope_retailers": current_users["retailers"],
                    "pending_approvals_in_scope": current_users["pending"],
                },
                **paginated,
            }
        )

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
        instance = serializer.instance
        old_scope = AdministratorScope.objects.filter(user=instance).select_related(
            "location"
        ).first()
        previous = (
            "Nationwide"
            if old_scope and old_scope.level == AdministratorScope.Level.GLOBAL
            else str(old_scope.location)
            if old_scope and old_scope.location_id
            else "Unassigned"
        )
        user = serializer.save()
        new_scope = AdministratorScope.objects.filter(user=user).select_related(
            "location"
        ).first()
        current = (
            "Nationwide"
            if new_scope and new_scope.level == AdministratorScope.Level.GLOBAL
            else str(new_scope.location)
            if new_scope and new_scope.location_id
            else "Unassigned"
        )
        self._audit(
            "admin_account_updated",
            user.email,
            f"Scope: {previous} -> {current}",
        )

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
        if user.status in (AccountStatus.DEACTIVATED, AccountStatus.SUSPENDED):
            user.reinstate(actor=request.user)
        self._audit("admin_account_reinstated", user.email)
        return Response(
            {
                "success": True,
                "message": f"{user.full_name} reinstated.",
                "user": DirectoryUserSerializer(user).data,
            }
        )

    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        user = self.get_object()
        if user == request.user:
            return Response(
                {"success": False, "error": "You cannot suspend your own account."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if user.status != AccountStatus.SUSPENDED:
            user.suspend(actor=request.user, reason=(request.data.get("reason") or "").strip())
        self._audit(
            "staff_account_suspended",
            user.email,
            (request.data.get("reason") or "").strip(),
        )
        return Response(
            {
                "success": True,
                "message": f"{user.full_name} suspended.",
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
        registration = getattr(user, "registration", None)
        registration_decision_recorded = False
        if registration and not registration.legacy_registration:
            from registrations.models import RegistrationReview, RegistrationStatus
            from registrations.services import record_registration_decision

            if decision == "APPROVE" and registration.status == RegistrationStatus.APPROVED:
                return Response(
                    {"success": False, "error": "This registration is already approved."},
                    status=status.HTTP_409_CONFLICT,
                )
            if decision == "APPROVE" and registration.status not in (
                RegistrationStatus.SUBMITTED,
                RegistrationStatus.CHANGES_REQUESTED,
            ):
                return Response(
                    {"success": False, "error": "This registration is not awaiting review."},
                    status=status.HTTP_409_CONFLICT,
                )
            if decision in ("APPROVE", "REJECT") and registration.status in (
                RegistrationStatus.SUBMITTED,
                RegistrationStatus.CHANGES_REQUESTED,
            ):
                registration = record_registration_decision(
                    registration.pk,
                    request.user,
                    decision,
                    reason,
                )
                user = registration.user
                registration_decision_recorded = True
            elif decision == "REACTIVATE" and registration.status != RegistrationStatus.APPROVED:
                return Response(
                    {"success": False, "error": "Resubmit and approve this registration before reactivating the account."},
                    status=status.HTTP_409_CONFLICT,
                )

        if decision == "APPROVE" and not registration_decision_recorded:
            user.approve(actor=request.user)
            if registration and not registration.legacy_registration:
                registration.status = RegistrationStatus.APPROVED
                registration.save(update_fields=["status", "updated_at"])
                RegistrationReview.objects.create(
                    registration=registration,
                    reviewer=request.user,
                    action=RegistrationReview.Action.APPROVED,
                    reason=reason,
                )
        elif decision == "REJECT" and not registration_decision_recorded:
            user.reject(reason, actor=request.user)
            if registration and not registration.legacy_registration:
                registration.status = RegistrationStatus.REJECTED
                registration.save(update_fields=["status", "updated_at"])
                RegistrationReview.objects.create(
                    registration=registration,
                    reviewer=request.user,
                    action=RegistrationReview.Action.REJECTED,
                    reason=reason,
                )
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


@extend_schema(request=LoginUnlockSerializer, responses=OpenApiTypes.OBJECT)
class LoginUnlockView(APIView):
    """POST /api/v1/superadmin/users/{id}/unlock-login/."""

    permission_classes = [IsSuperAdmin]

    def post(self, request, pk):
        serializer = LoginUnlockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            user = User.objects.select_for_update().filter(pk=pk).first()
            if user is None:
                return Response(
                    {"success": False, "error": "User not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            if user.locked_until is None:
                return Response(
                    {"success": False, "error": "This account is not locked."},
                    status=status.HTTP_409_CONFLICT,
                )
            previous_expiry = user.locked_until.isoformat()
            user.locked_until = None
            user.failed_login_attempts = 0
            user.save(update_fields=["locked_until", "failed_login_attempts"])
            AuditLog.objects.create(
                actor=request.user,
                action="account_login_unlocked",
                target=str(user.pk),
                detail=json.dumps(
                    {
                        "previous_locked_until": previous_expiry,
                        "reason": serializer.validated_data["reason"],
                    },
                    sort_keys=True,
                ),
            )
        return Response(
            {
                "success": True,
                "message": f"Login lockout cleared for {user.full_name}.",
                "user": DirectoryUserSerializer(user).data,
            }
        )


# ---------------------------------------------------------------------------
# FR-SA-01 — unrestricted read access across modules
# ---------------------------------------------------------------------------
@extend_schema(responses=OpenApiTypes.OBJECT)
class SuperAdminUsersListView(APIView):
    """Paginated and filterable full user directory for Super Admin."""

    permission_classes = [IsSuperAdmin]

    def get(self, request):
        from django.db.models import Q
        from django.utils.dateparse import parse_date
        from rest_framework.exceptions import ValidationError
        from rest_framework.pagination import PageNumberPagination

        from .serializers import DirectoryUserSerializer

        queryset = User.objects.all().order_by("-created_at", "id")
        role = request.query_params.get("role")
        if role:
            if role not in dict(Role.choices):
                raise ValidationError({"role": "Select a valid user role."})
            queryset = queryset.filter(role=role)

        status = request.query_params.get("status")
        if status:
            if status not in dict(AccountStatus.choices):
                raise ValidationError({"status": "Select a valid account status."})
            queryset = queryset.filter(status=status)

        search = (request.query_params.get("search") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(full_name__icontains=search)
                | Q(email__icontains=search)
                | Q(phone__icontains=search)
                | Q(location__icontains=search)
            )

        created_from = request.query_params.get("created_from")
        created_to = request.query_params.get("created_to")
        start_date = parse_date(created_from) if created_from else None
        end_date = parse_date(created_to) if created_to else None
        if created_from and start_date is None:
            raise ValidationError({"created_from": "Use YYYY-MM-DD format."})
        if created_to and end_date is None:
            raise ValidationError({"created_to": "Use YYYY-MM-DD format."})
        if start_date and end_date and start_date > end_date:
            raise ValidationError(
                {"created_to": "Must be on or after created_from."}
            )
        if start_date:
            queryset = queryset.filter(created_at__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__date__lte=end_date)

        paginator = PageNumberPagination()
        paginator.page_size = 20
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = DirectoryUserSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


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
        "max_failed_login_attempts",
        "lockout_duration_minutes",
        "text_messaging_enabled",
        "voice_messaging_enabled",
    )

    def get(self, request):
        config = PlatformSettings.load()
        return Response({"success": True, "settings": self._serialize(config)})

    def patch(self, request):
        serializer = PlatformSettingsUpdateSerializer(
            data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        reason = values.pop("reason", "").strip()
        critical_fields = {
            "maintenance_mode",
            "max_failed_login_attempts",
            "lockout_duration_minutes",
            "text_messaging_enabled",
            "voice_messaging_enabled",
        }
        config = PlatformSettings.load()
        previous = {}
        changed = {}
        for field in self.FIELDS:
            if field in values and getattr(config, field) != values[field]:
                previous[field] = getattr(config, field)
                setattr(config, field, values[field])
                changed[field] = values[field]
        if not changed:
            return Response(
                {
                    "success": False,
                    "error": f"No settings supplied. Valid fields: {', '.join(self.FIELDS)}.",
                },
                status=400,
            )
        if critical_fields.intersection(changed) and not reason:
            raise ValidationError(
                {"reason": "Provide a reason when changing security or access policies."}
            )
        config.updated_by = request.user
        config.save()

        from .models import AuditLog

        AuditLog.objects.create(
            actor=request.user,
            action="platform_settings_updated",
            target="platform",
            detail=json.dumps(
                {
                    "reason": reason,
                    "previous": previous,
                    "new": changed,
                },
                sort_keys=True,
            ),
        )

        if config.announcement and previous.get("announcement") != config.announcement:
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
            "max_failed_login_attempts": config.max_failed_login_attempts,
            "lockout_duration_minutes": config.lockout_duration_minutes,
            "text_messaging_enabled": config.text_messaging_enabled,
            "voice_messaging_enabled": config.voice_messaging_enabled,
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
    """Read-only administrator activity, filtered to the caller's scope."""

    permission_classes = [IsUserAdmin]
    serializer_class = AuditLogSerializer

    def get_queryset(self):
        queryset = AuditLog.objects.select_related("actor").order_by("-created_at")
        actor = self.request.user
        if actor.role != Role.SUPER_ADMIN:
            managed_ids = manageable_admins_for(
                actor,
                User.objects.all(),
            ).values("pk")
            visible_emails = users_visible_to_admin(actor).values("email")
            queryset = queryset.filter(
                Q(actor_id=actor.pk)
                | Q(actor_id__in=managed_ids)
                | Q(target__in=visible_emails)
            )

        actor_search = (self.request.query_params.get("administrator") or "").strip()
        if actor_search:
            queryset = queryset.filter(
                Q(actor__full_name__icontains=actor_search)
                | Q(actor__email__icontains=actor_search)
            )
        actor_role = self.request.query_params.get("role")
        if actor_role:
            queryset = queryset.filter(actor__role=actor_role)
        action = (self.request.query_params.get("action") or "").strip()
        if action:
            queryset = queryset.filter(action__icontains=action)
        target = (self.request.query_params.get("target") or "").strip()
        if target:
            queryset = queryset.filter(target__icontains=target)
        for parameter, lookup in (
            ("from", "created_at__date__gte"),
            ("to", "created_at__date__lte"),
        ):
            raw = self.request.query_params.get(parameter)
            if raw:
                parsed = parse_date(raw)
                if parsed is None:
                    raise ValidationError({parameter: "Use an ISO date (YYYY-MM-DD)."})
                queryset = queryset.filter(**{lookup: parsed})

        location_id = self.request.query_params.get("location_id")
        if location_id:
            location = AdministrativeLocation.objects.filter(
                pk=location_id,
                active=True,
            ).first()
            if location is None:
                raise ValidationError({"location_id": "Choose an active location."})
            descendants = location_descendant_ids(location)
            registration_user_ids = UserRegistration.objects.filter(
                location_id__in=descendants
            ).values("user_id")
            staff_user_ids = AdministratorScope.objects.filter(
                location_id__in=descendants
            ).values("user_id")
            users_at_location = User.objects.filter(
                Q(pk__in=registration_user_ids) | Q(pk__in=staff_user_ids)
            )
            queryset = queryset.filter(
                Q(target__in=users_at_location.values("email"))
                | Q(actor_id__in=users_at_location.values("pk"))
            )

        registration_status = self.request.query_params.get("registration_status")
        if registration_status:
            if registration_status not in RegistrationStatus.values:
                raise ValidationError(
                    {"registration_status": "Choose a valid registration status."}
                )
            matching_emails = User.objects.filter(
                registration__status=registration_status
            ).values("email")
            queryset = queryset.filter(target__in=matching_emails)
        license_status = self.request.query_params.get("license_status")
        if license_status:
            valid_license_statuses = {
                choice.value for choice in RegistrationDocument.VerificationStatus
            }
            if license_status not in valid_license_statuses:
                raise ValidationError(
                    {"license_status": "Choose PENDING, VERIFIED, or REJECTED."}
                )
            matching_emails = User.objects.filter(
                registration__documents__verification_status=license_status
            ).values("email")
            queryset = queryset.filter(target__in=matching_emails).distinct()
        return queryset
