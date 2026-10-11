from django.core import signing
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import authentication, exceptions
from rest_framework.authentication import get_authorization_header

from users.models import AccountStatus, User

from .models import RegistrationStatus

REGISTRATION_TOKEN_SALT = "greenpath.registration-completion"
REGISTRATION_TOKEN_MAX_AGE = 60 * 60 * 24 * 7


def make_registration_token(user):
    return signing.dumps(
        {"user_id": str(user.pk), "purpose": "complete-registration"},
        salt=REGISTRATION_TOKEN_SALT,
    )


class RegistrationCompletionAuthentication(authentication.BaseAuthentication):
    """Authenticate only completion endpoints with a purpose-limited token."""

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts:
            return None
        if len(parts) != 2 or parts[0].lower() != b"bearer":
            raise exceptions.AuthenticationFailed("Invalid registration credential.")

        try:
            payload = signing.loads(
                parts[1].decode("utf-8"),
                salt=REGISTRATION_TOKEN_SALT,
                max_age=REGISTRATION_TOKEN_MAX_AGE,
            )
            if payload.get("purpose") != "complete-registration":
                raise exceptions.AuthenticationFailed("Invalid registration credential.")
            user = User.objects.get(
                pk=payload.get("user_id"),
                status__in=(AccountStatus.PENDING, AccountStatus.REJECTED),
            )
            registration = user.registration
        except (
            signing.BadSignature,
            signing.SignatureExpired,
            ValueError,
            User.DoesNotExist,
            ObjectDoesNotExist,
        ):
            raise exceptions.AuthenticationFailed(
                "Registration credential is invalid or expired."
            )

        if registration.status not in (
            RegistrationStatus.DRAFT,
            RegistrationStatus.CHANGES_REQUESTED,
            RegistrationStatus.REJECTED,
        ):
            raise exceptions.AuthenticationFailed("Registration is no longer editable.")
        return user, payload

    def authenticate_header(self, request):
        return "Bearer"
