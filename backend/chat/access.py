from django.db.models import Q

from users.models import AccountStatus, Role, User


ALLOWED_COUNTERPARTIES = {
    Role.FARMER: {
        Role.WHOLESALER,
        Role.USER_ADMIN,
        Role.FINANCIAL_MANAGER,
        Role.SUPER_ADMIN,
    },
    Role.WHOLESALER: {
        Role.FARMER,
        Role.RETAILER,
        Role.USER_ADMIN,
        Role.FINANCIAL_MANAGER,
        Role.SUPER_ADMIN,
    },
    Role.RETAILER: {
        Role.WHOLESALER,
        Role.USER_ADMIN,
        Role.SUPER_ADMIN,
    },
    Role.USER_ADMIN: {
        Role.FARMER,
        Role.WHOLESALER,
        Role.RETAILER,
        Role.USER_ADMIN,
        Role.FINANCIAL_MANAGER,
        Role.SUPER_ADMIN,
    },
    Role.FINANCIAL_MANAGER: {
        Role.FARMER,
        Role.WHOLESALER,
        Role.USER_ADMIN,
        Role.SUPER_ADMIN,
    },
    Role.SUPER_ADMIN: set(Role.values),
}


def _user_admin_scopes_related(actor, other):
    from registrations.models import AdministratorScope
    from registrations.services import location_descendant_ids

    actor_scope = AdministratorScope.objects.select_related("location").filter(
        user_id=actor.pk
    ).first()
    other_scope = AdministratorScope.objects.select_related("location").filter(
        user_id=other.pk
    ).first()
    if actor_scope is None or other_scope is None:
        return False
    if (
        actor_scope.level == AdministratorScope.Level.GLOBAL
        or other_scope.level == AdministratorScope.Level.GLOBAL
    ):
        return True
    if (
        actor_scope.location is None
        or other_scope.location is None
        or not actor_scope.location.active
        or not other_scope.location.active
    ):
        return False

    actor_subtree = set(location_descendant_ids(actor_scope.location))
    if other_scope.location_id in actor_subtree:
        return True
    other_subtree = set(location_descendant_ids(other_scope.location))
    return actor_scope.location_id in other_subtree


def can_communicate(actor, other):
    """Return whether the actor may open or access a conversation with a user."""
    if not actor or not other or actor.pk == other.pk:
        return False
    if other.role not in ALLOWED_COUNTERPARTIES.get(actor.role, set()):
        return False
    if actor.role == Role.USER_ADMIN and other.role == Role.USER_ADMIN:
        return _user_admin_scopes_related(actor, other)
    return True


def related_user_admin_ids(actor):
    """Return administrator IDs that may share a conversation with this admin."""
    from registrations.models import AdministratorScope
    from registrations.services import (
        administrator_scope_for,
        location_descendant_ids,
    )

    permitted_ids = {actor.pk}
    scope = administrator_scope_for(actor)
    if scope is None:
        return permitted_ids
    if scope.level == AdministratorScope.Level.GLOBAL:
        permitted_ids.update(
            User.objects.filter(
                role=Role.USER_ADMIN,
                administrative_scope__isnull=False,
            ).values_list("pk", flat=True)
        )
        return permitted_ids
    if scope.location is None or not scope.location.active:
        return permitted_ids

    related_location_ids = set(location_descendant_ids(scope.location))
    ancestor = scope.location.parent
    while ancestor is not None:
        if ancestor.active:
            related_location_ids.add(ancestor.pk)
        ancestor = ancestor.parent
    permitted_ids.update(
        User.objects.filter(role=Role.USER_ADMIN)
        .filter(
            Q(administrative_scope__level=AdministratorScope.Level.GLOBAL)
            | Q(administrative_scope__location_id__in=related_location_ids)
        )
        .values_list("pk", flat=True)
    )
    return permitted_ids


def eligible_staff_recipients(actor, search=""):
    """Return active staff accounts the actor is allowed to contact."""
    candidates = User.objects.filter(
        role__in=(Role.USER_ADMIN, Role.FINANCIAL_MANAGER, Role.SUPER_ADMIN),
        status=AccountStatus.APPROVED,
        is_active=True,
    ).exclude(pk=actor.pk)
    search = (search or "").strip()
    if search:
        candidates = candidates.filter(
            Q(full_name__icontains=search)
            | Q(role__icontains=search)
            | Q(location__icontains=search)
        )
    candidates = candidates.select_related(
        "administrative_scope__location"
    ).order_by("full_name", "pk")
    return [candidate for candidate in candidates if can_communicate(actor, candidate)]


def can_access_channel(actor, channel):
    if not channel.participants.filter(pk=actor.pk).exists():
        return False
    return all(
        can_communicate(actor, participant)
        for participant in channel.participants.exclude(pk=actor.pk)
    )


def can_moderate_voice(actor, channel):
    """Limit pending audio review to finance staff and scoped administrators."""
    if actor.role in (Role.FINANCIAL_MANAGER, Role.SUPER_ADMIN):
        return True
    if actor.role != Role.USER_ADMIN:
        return False

    from registrations.services import users_visible_to_admin

    participant_ids = list(channel.participants.values_list("pk", flat=True))
    if not participant_ids:
        return False
    return users_visible_to_admin(actor).filter(pk__in=participant_ids).count() == len(
        participant_ids
    )
