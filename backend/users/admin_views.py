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

SORTABLE = ("created_at", "-created_at", "full_name", "-full_name")


def _apply_filters(queryset, params):
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
    ordering = params.get("ordering", "-created_at")
    if ordering in SORTABLE:
        queryset = queryset.order_by(ordering)
    return queryset


class PendingUsersView(generics.ListAPIView):
    """GET /api/v1/admin/pending-users/ — the User Admin approval queue (FR-UA-01)."""

    permission_classes = [IsUserAdmin]
    serializer_class = DirectoryUserSerializer

    def get_queryset(self):
        return _apply_filters(
            User.objects.filter(status=AccountStatus.PENDING),
            self.request.query_params,
        )


class AllUsersView(generics.ListAPIView):
    """GET /api/v1/admin/users/ — full user directory with filters (FR-UA-03)."""

    permission_classes = [IsUserAdmin]
    serializer_class = DirectoryUserSerializer

    def get_queryset(self):
        return _apply_filters(User.objects.all(), self.request.query_params)


class _UserActionView(APIView):
    permission_classes = [IsUserAdmin]

    def get_user(self, pk):
        return User.objects.filter(pk=pk).first()


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

        created = notify(
            user_ids=user_ids,
            roles=[role] if role else None,
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
