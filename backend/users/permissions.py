"""Role-based access control (doc 4.10, FR-* per role).

Every protected endpoint is guarded by a permission class that matches the
*required role* column of the endpoint table in doc 5.1.5.  ``SUPER_ADMIN`` is
the governance backstop (FR-SA-01: unrestricted read access across modules) and
therefore bypasses commercial-role checks unless a permission explicitly opts
out via ``allow_super_admin = False``.
"""
from rest_framework import permissions

from .models import Role

ADMIN_ROLES = ("USER_ADMIN", "FINANCIAL_MANAGER", "SUPER_ADMIN")


class IsRole(permissions.BasePermission):
    """Base RBAC check against the role claim resolved from the JWT."""

    allowed_roles: tuple = ()
    allow_super_admin: bool = True

    def __init__(self, allowed_roles=None):
        # Allows a view to build the role requirement dynamically, e.g.
        # ``IsAuthenticatedRole(("WHOLESALER", "RETAILER"))``.
        if allowed_roles is not None:
            self.allowed_roles = tuple(allowed_roles)
        super().__init__()

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if self.allow_super_admin and user.role == Role.SUPER_ADMIN:
            return True
        return user.role in self.allowed_roles


class IsAuthenticatedRole(IsRole):
    """Any authenticated user holding one of the supplied roles."""


class IsFarmer(IsRole):
    allowed_roles = ("FARMER",)


class IsWholesaler(IsRole):
    allowed_roles = ("WHOLESALER",)


class IsRetailer(IsRole):
    allowed_roles = ("RETAILER",)


class IsUserAdmin(IsRole):
    allowed_roles = ("USER_ADMIN",)


class IsFinancialManager(IsRole):
    allowed_roles = ("FINANCIAL_MANAGER",)


class IsSuperAdmin(IsRole):
    allowed_roles = ("SUPER_ADMIN",)
    allow_super_admin = False

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and user.is_authenticated and user.role == Role.SUPER_ADMIN
        )


class IsAdminRole(IsRole):
    """User Admin or Financial Manager (Super Admin allowed by default)."""

    allowed_roles = ("USER_ADMIN", "FINANCIAL_MANAGER")


class IsFinancialStaff(IsRole):
    """Financial Manager only — sensitive financial data (doc 4.10)."""

    allowed_roles = ("FINANCIAL_MANAGER",)


class CanStartConversation(permissions.BasePermission):
    """Restrict who may open a chat channel (FR-F-08 / FR-W-06 / FR-R-04).

    The counterparty check itself needs the target user id from the request
    body, so it is deferred to the view which has the full queryset context.
    """

    allowed_roles = ("FARMER", "WHOLESALER", "RETAILER", "USER_ADMIN", "FINANCIAL_MANAGER")

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return user.role in self.allowed_roles


class IsChatParticipant(permissions.BasePermission):
    """Object level: only members of a channel may read or post to it."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        channel = getattr(obj, "channel", None) or obj
        return bool(
            user
            and user.is_authenticated
            and channel.participants.filter(pk=user.pk).exists()
        )


class IsListingReaderOrOwner(permissions.BasePermission):
    """Marketplace read access with an owner exemption.

    A seller must always be able to open the detail page of a listing they
    created, including DRAFT/INACTIVE/SOLD rows that
    ``ProductQuerySet.visible_to`` deliberately hides from the marketplace.
    Browsing *another* party's marketplace stays restricted to the reader
    roles of doc 5.1.5 — the owner exemption never widens ``list`` access.
    """

    reader_roles: tuple = ()
    creator_roles: tuple = ()

    def __init__(self, reader_roles=None, creator_roles=None):
        if reader_roles is not None:
            self.reader_roles = tuple(reader_roles)
        if creator_roles is not None:
            self.creator_roles = tuple(creator_roles)
        super().__init__()

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        # Super Admin is the governance backstop (FR-SA-01).
        if user.role == Role.SUPER_ADMIN:
            return True
        # A role that may publish into this marketplace passes the role gate
        # here; the object check below then limits it to its own rows.
        return user.role in self.reader_roles or user.role in self.creator_roles

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.role == Role.SUPER_ADMIN:
            return True
        if getattr(obj, "owner", None) == user:
            return True
        return user.role in self.reader_roles


class IsOwnerOrAdmin(permissions.BasePermission):
    """Object level: the listing/record owner, or an admin reviewing it."""

    admin_roles = ADMIN_ROLES

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.role in self.admin_roles:
            return True
        owner = getattr(obj, "owner", None) or getattr(obj, "submitted_by", None)
        return owner == user
