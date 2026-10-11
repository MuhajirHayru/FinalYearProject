"""User Admin module endpoints (doc 3.3.1.4 — FR-UA-01 .. FR-UA-05)."""
from django.db.models import Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status, views
from rest_framework.response import Response
from rest_framework.views import APIView

from notifications.services import notify

from .models import AccountStatus, Role, User
from .permissions import IsUserAdmin
from .serializers import (
    BroadcastMessageSerializer,
    DirectoryUserSerializer,
    RejectUserSerializer,
)
from registrations.models import UserRegistration
from registrations.services import users_visible_to_admin

SORTABLE = ("created_at", "-created_at", "full_name", "-full_name")


def _apply_filters(queryset, params):
    from django.utils.dateparse import parse_date
    from rest_framework.exceptions import ValidationError

    role = params.get("role")
    if role and role != "ALL":
        queryset = queryset.filter(role=role)
    search = (params.get("search") or "").strip()
    if search:
        queryset = queryset.filter(
            Q(full_name__icontains=search)
            | Q(email__icontains=search)
            | Q(location__icontains=search)
        )
    status_param = params.get("status")
    if status_param and status_param != "ALL":
        queryset = queryset.filter(status=status_param)
    created_from = params.get("created_from")
    created_to = params.get("created_to")
    start_date = parse_date(created_from) if created_from else None
    end_date = parse_date(created_to) if created_to else None
    if created_from and start_date is None:
        raise ValidationError({"created_from": "Use YYYY-MM-DD format."})
    if created_to and end_date is None:
        raise ValidationError({"created_to": "Use YYYY-MM-DD format."})
    if start_date and end_date and start_date > end_date:
        raise ValidationError({"created_to": "Must be on or after created_from."})
    if start_date:
        queryset = queryset.filter(created_at__date__gte=start_date)
    if end_date:
        queryset = queryset.filter(created_at__date__lte=end_date)
    ordering = params.get("ordering", "-created_at")
    if ordering in SORTABLE:
        queryset = queryset.order_by(ordering)
    return queryset


class PendingUsersView(generics.ListAPIView):
    """GET /api/v1/admin/pending-users/ — the User Admin approval queue (FR-UA-01)."""

    permission_classes = [IsUserAdmin]
    serializer_class = DirectoryUserSerializer

    def get_queryset(self):
        queryset = users_visible_to_admin(self.request.user, User.objects.all())
        queryset = queryset.filter(status=AccountStatus.PENDING).filter(
            Q(registration__legacy_registration=True)
            | Q(registration__isnull=True)
        )
        return _apply_filters(queryset, self.request.query_params).distinct()


class AllUsersView(generics.ListAPIView):
    """GET /api/v1/admin/users/ — full user directory with filters (FR-UA-03)."""

    permission_classes = [IsUserAdmin]
    serializer_class = DirectoryUserSerializer

    def get_queryset(self):
        queryset = users_visible_to_admin(self.request.user, User.objects.all())
        return _apply_filters(queryset, self.request.query_params).distinct()


class _UserActionView(APIView):
    permission_classes = [IsUserAdmin]

    def get_user(self, pk):
        queryset = users_visible_to_admin(self.request.user, User.objects.all())
        return queryset.filter(pk=pk).first()


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
class ApproveUserView(_UserActionView):
    """POST /api/v1/admin/users/{id}/approve/ (FR-UA-02, UC-05)."""

    def post(self, request, pk):
        user = self.get_user(pk)
        if user is None:
            return Response({"success": False, "error": "User not found."}, status=404)
        if user.status == AccountStatus.APPROVED:
            return Response(
                {"success": False, "error": "User is already approved."}, status=400
            )
        registration = UserRegistration.objects.filter(user=user).first()
        if registration and not registration.legacy_registration:
            from registrations.services import record_registration_decision

            record_registration_decision(registration.pk, request.user, "APPROVE")
            user.refresh_from_db()
            return Response(
                {
                    "success": True,
                    "message": f"{user.full_name} approved.",
                    "user": DirectoryUserSerializer(user).data,
                }
            )
        # Approval notification is emitted by the user_status_changed domain event.
        user.approve(actor=request.user)
        return Response(
            {
                "success": True,
                "message": f"{user.full_name} approved.",
                "user": DirectoryUserSerializer(user).data,
            }
        )


@extend_schema(request=RejectUserSerializer, responses=OpenApiTypes.OBJECT)
class RejectUserView(_UserActionView):
    """POST /api/v1/admin/users/{id}/reject/ with an optional reason (FR-UA-02)."""

    def post(self, request, pk):
        user = self.get_user(pk)
        if user is None:
            return Response({"success": False, "error": "User not found."}, status=404)
        if user.status == AccountStatus.REJECTED:
            return Response(
                {"success": False, "error": "User is already rejected."}, status=400
            )
        reason = (request.data.get("reason") or "").strip()
        registration = UserRegistration.objects.filter(user=user).first()
        if registration and not registration.legacy_registration:
            from registrations.services import record_registration_decision

            record_registration_decision(
                registration.pk,
                request.user,
                "REJECT",
                reason,
            )
            user.refresh_from_db()
            return Response(
                {
                    "success": True,
                    "message": f"{user.full_name} rejected.",
                    "user": DirectoryUserSerializer(user).data,
                }
            )
        # Rejection notification is emitted by the user_status_changed domain event.
        user.reject(reason, actor=request.user)
        return Response(
            {
                "success": True,
                "message": f"{user.full_name} rejected.",
                "user": DirectoryUserSerializer(user).data,
            }
        )


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
class SuspendUserView(_UserActionView):
    """POST /api/v1/admin/users/{id}/suspend/ — suspend or reinstate (FR-UA-03).

    Only the Super Admin may act on Admin sub-role accounts.
    """

    def post(self, request, pk):
        user = self.get_user(pk)
        if user is None:
            return Response({"success": False, "error": "User not found."}, status=404)
        if user.role in (Role.USER_ADMIN, Role.FINANCIAL_MANAGER, Role.SUPER_ADMIN):
            if request.user.role != Role.SUPER_ADMIN:
                return Response(
                    {
                        "success": False,
                        "error": "Only the Super Admin can suspend admin accounts.",
                    },
                    status=403,
                )
        if user == request.user:
            return Response(
                {"success": False, "error": "You cannot suspend your own account."},
                status=400,
            )

        if user.status == AccountStatus.SUSPENDED:
            user.reinstate(actor=request.user)
            action = "reinstated"
        else:
            user.suspend(actor=request.user)
            action = "suspended"

        return Response(
            {
                "success": True,
                "message": f"{user.full_name} {action}.",
                "user": DirectoryUserSerializer(user).data,
            }
        )


@extend_schema(request=BroadcastMessageSerializer, responses=OpenApiTypes.OBJECT)
class BroadcastMessageView(APIView):
    """POST /api/v1/admin/messages/ — broadcast or individual message (FR-UA-04).

    Body accepts either ``role`` (broadcast to a whole role) or ``user_ids``
    (direct message).  One of the two is required.
    """

    permission_classes = [IsUserAdmin]

    def post(self, request):
        message = (request.data.get("message") or "").strip()
        if not message:
            return Response(
                {"success": False, "error": "Message body is required."}, status=400
            )

        user_ids = request.data.get("user_ids")
        role = request.data.get("role")
        if not user_ids and not role:
            return Response(
                {
                    "success": False,
                    "error": "Provide either user_ids or a role to target.",
                },
                status=400,
            )

        visible_users = users_visible_to_admin(request.user, User.objects.all())
        if user_ids:
            if not isinstance(user_ids, list) or not user_ids:
                return Response(
                    {"success": False, "error": "user_ids must be a non-empty list."},
                    status=400,
                )
            recipients = list(
                visible_users.filter(id__in=user_ids).values_list("id", flat=True)
            )
            if len(recipients) != len(set(user_ids)):
                return Response(
                    {"success": False, "error": "One or more recipients are outside your scope."},
                    status=404,
                )
        else:
            recipients = list(
                visible_users.filter(role=role).values_list("id", flat=True)
            )
        created = notify(
            user_ids=recipients,
            type="SYSTEM",
            message=message,
            actor=request.user,
        )
        return Response(
            {
                "success": True,
                "message": f"Message delivered to {len(created)} user(s).",
                "recipients": len(created),
            },
            status=201,
        )
