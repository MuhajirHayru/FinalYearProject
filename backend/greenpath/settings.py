"""Django settings for the Green Path platform (per final year project doc)."""
import os
from datetime import timedelta
from pathlib import Path

from corsheaders.defaults import default_headers

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-greenpath-dev-key-change-in-production",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"

ALLOWED_HOSTS = os.environ.get(
    "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1"
).split(",")

# Production hardening (NFR-01/02). Every flag is environment driven so a
# development machine keeps the relaxed defaults while a deployment can turn
# on HTTPS-only cookies, HSTS and the SSL redirect with no code change.
SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SECURE_SSL_REDIRECT", "0") == "1"
SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0
SESSION_COOKIE_SECURE = os.environ.get("DJANGO_SECURE_COOKIES", "0") == "1"
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SECURE_PROXY_SSL_HEADER = (
    ("HTTP_X_FORWARDED_PROTO", "https") if os.environ.get("DJANGO_BEHIND_PROXY", "0") == "1" else None
)
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "channels",
    "drf_spectacular",
    "users",
    "products",
    "chat",
    "payments",
    "notifications",
    "dashboard",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # CsrfViewMiddleware is intentionally omitted: every mutating endpoint is
    # authenticated by a Bearer access token held in JavaScript, and the only
    # cookie (the refresh token) is httpOnly + SameSite=Lax + CORS-restricted,
    # so it is never attached to a cross-site POST. See CSRF_TRUSTED_ORIGINS.
]

ROOT_URLCONF = "greenpath.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # Project-level 404/500 pages; required once DEBUG is off.
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "greenpath.wsgi.application"
ASGI_APPLICATION = "greenpath.asgi.application"

# Database: PostgreSQL in production (per doc), SQLite for development.
DATABASES = {
    "default": {
        "ENGINE": os.environ.get("DB_ENGINE", "django.db.backends.sqlite3"),
        "NAME": os.environ.get("DB_NAME", BASE_DIR / "db.sqlite3"),
        "USER": os.environ.get("DB_USER", ""),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", ""),
        "PORT": os.environ.get("DB_PORT", ""),
    }
}

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Addis_Ababa"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# CORS / Cookies (Next.js dev server on :3000)
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = [
    origin
    for origin in os.environ.get(
        "DJANGO_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin
]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = (*default_headers, "idempotency-key")
# The refresh token lives in an httpOnly cookie, so browser-initiated writes are
# additionally constrained by CORS pre-flight plus the cookie SameSite policy.
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS

# ---------------------------------------------------------------------------
# REST Framework + JWT (doc: access token 1h body, refresh token 7d cookie)
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "greenpath.exceptions.api_exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Green Path API",
    "DESCRIPTION": "AI-Integrated Farm-to-Marketplace System REST API",
    "VERSION": "1.0.0",
    # Several models expose a "status" choice set with different members
    # (account, listing, payment, order); name them so the schema is stable.
    "ENUM_NAME_OVERRIDES": {
        "AccountStatusEnum": "users.models.AccountStatus.choices",
        "ProductStatusEnum": "products.models.ProductStatus.choices",
        "PaymentStatusEnum": "payments.models.PaymentStatus.choices",
        "OrderStatusEnum": "payments.models.OrderStatus.choices",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

REFRESH_COOKIE_KEY = "greenpath_refresh"
REFRESH_COOKIE_HTTPONLY = True
REFRESH_COOKIE_SAMESITE = "Lax"
REFRESH_COOKIE_SECURE = os.environ.get("DJANGO_SECURE_COOKIES", "0") == "1"
REFRESH_COOKIE_PATH = "/"

# ---------------------------------------------------------------------------
# Django Channels (WebSocket chat / notifications). Redis in prod, in-memory dev.
# ---------------------------------------------------------------------------
CHANNEL_LAYERS = {
    "default": (
        {"BACKEND": "channels_redis.core.RedisChannelLayer",
         "CONFIG": {"hosts": [os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")]}}
        if os.environ.get("USE_REDIS", "0") == "1"
        else {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    ),
}

# Frontend origin used when pushing WS URLs to clients (dev only)
FRONTEND_WS_HOST = os.environ.get("FRONTEND_WS_HOST", "localhost:8000")
PRESENCE_TIMEOUT_SECONDS = int(os.environ.get("PRESENCE_TIMEOUT_SECONDS", "90"))
PRESENCE_HEARTBEAT_SECONDS = int(os.environ.get("PRESENCE_HEARTBEAT_SECONDS", "25"))

# Chapa's hosted checkout uses server-side API calls. Only test credentials are
# accepted by the integration; production payments are deliberately disabled.
CHAPA_TEST_MODE = os.environ.get("CHAPA_TEST_MODE", "1") == "1"
CHAPA_SECRET_KEY = os.environ.get("CHAPA_SECRET_KEY", "")
CHAPA_PUBLIC_KEY = os.environ.get("CHAPA_PUBLIC_KEY", "")
CHAPA_ENCRYPTION_KEY = os.environ.get("CHAPA_ENCRYPTION_KEY", "")
CHAPA_WEBHOOK_SECRET = os.environ.get("CHAPA_WEBHOOK_SECRET", "")
CHAPA_API_BASE_URL = "https://api.chapa.co/v1"
CHAPA_TIMEOUT_SECONDS = 15
BANK_ACCOUNT_ENCRYPTION_KEY = os.environ.get("BANK_ACCOUNT_ENCRYPTION_KEY", "")
FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://localhost:3000")
CHAPA_CALLBACK_URL = os.environ.get(
    "CHAPA_CALLBACK_URL",
    "http://localhost:8000/api/v1/wallet/chapa/webhook/",
)
