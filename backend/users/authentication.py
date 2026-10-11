from django.conf import settings
from django.utils.crypto import constant_time_compare, salted_hmac
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


def password_token_version(user):
    return salted_hmac(
        "users.password-token-version",
        user.password,
        secret=settings.SECRET_KEY,
    ).hexdigest()


def token_matches_password(token, user):
    token_version = token.get("pwdv")
    if token_version is not None:
        return constant_time_compare(token_version, password_token_version(user))
    if user.password_changed_at is not None:
        issued_at = token.get("iat")
        return bool(
            issued_at
            and int(issued_at) > int(user.password_changed_at.timestamp())
        )
    return True


class PasswordVersionJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if not token_matches_password(validated_token, user):
            raise AuthenticationFailed(
                "Your session is no longer valid. Please sign in again."
            )
        return user
