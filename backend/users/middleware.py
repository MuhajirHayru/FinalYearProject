"""WebSocket authentication middleware (doc 3.8 / 5.1.4).

Browsers cannot set headers on a WebSocket handshake, so the JWT is supplied
as a ``?token=<JWT>`` query parameter and validated here before the connection
is handed to the consumer.  An invalid or missing token yields an anonymous
scope, which every consumer then rejects with code 4401.
"""
from urllib.parse import parse_qs

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.conf import settings
from django.contrib.auth.models import AnonymousUser


@database_sync_to_async
def get_user_from_token(token):
    """Resolve a raw JWT to a User, or AnonymousUser when it is not usable.

    The access token is verified with simplejwt's own machinery so signature
    algorithm, expiry and the ``user_id`` claim handling stay in one place.
    """
    from rest_framework_simplejwt.exceptions import TokenError
    from rest_framework_simplejwt.tokens import AccessToken

    from users.models import AccountStatus, User

    try:
        access = AccessToken(token)
        user = User.objects.get(id=access["user_id"])
    except (TokenError, KeyError, User.DoesNotExist, ValueError, TypeError):
        return AnonymousUser()

    if user.status != AccountStatus.APPROVED or not user.is_active:
        return AnonymousUser()
    return user


def _read_token(scope):
    # 1) Query string: wss://host/ws/chat/<id>/?token=<JWT>
    query = parse_qs(scope.get("query_string", b"").decode(errors="ignore"))
    token = (query.get("token") or [None])[0]
    if token:
        return token

    # 2) Subprotocol header, used by clients that cannot put secrets in a URL.
    for header, value in scope.get("headers", []):
        if header == b"sec-websocket-protocol":
            candidate = value.decode(errors="ignore").split(",")[0].strip()
            if candidate and candidate != "bearer":
                return candidate
    return None


class JWTAuthMiddleware(BaseMiddleware):
    def __init__(self, inner):
        super().__init__(inner)

    async def __call__(self, scope, receive, send):
        scope = dict(scope)
        token = _read_token(scope)
        scope["user"] = await get_user_from_token(token) if token else AnonymousUser()
        return await self.inner(scope, receive, send)
