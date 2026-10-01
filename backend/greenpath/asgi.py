import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "greenpath.settings")

django_asgi_app = get_asgi_application()

from chat.routing import websocket_urlpatterns  # noqa: E402
from users.middleware import JWTAuthMiddleware  # noqa: E402

# Registers the domain-event signal receivers (doc 4.11.2). Must be imported
# after the app registry is populated.
import greenpath.signals  # noqa: E402, F401

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            JWTAuthMiddleware(AuthMiddlewareStack(URLRouter(websocket_urlpatterns)))
        ),
    }
)
