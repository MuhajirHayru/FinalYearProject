"""Settings used by the automated test suite (NFR-10).

Only test-irrelevant knobs are overridden: password hashing is switched to the
fast development hasher so the suite does not spend minutes in PBKDF2, and the
media root is redirected to a temporary directory so image-upload tests never
write into the repository.
"""
import tempfile

from .settings import *  # noqa: F401,F403

# PBKDF2 (1.2M iterations) dominates runtime when a test authenticates.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

MEDIA_ROOT = tempfile.mkdtemp(prefix="greenpath-test-media-")

# Keep the real-time layer fully in-process during tests.
CHANNEL_LAYERS = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}

# WebsocketCommunicator handshakes without an Origin header, so
# AllowedHostsOriginValidator falls back to comparing the Host header against
# ALLOWED_HOSTS. Without this the handshake is refused before the consumer runs.
ALLOWED_HOSTS = ["*"]

# Password strength rules still apply to the serializers; only hashing is relaxed.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Let pytest report the real traceback instead of Django's 500 machinery, whose
# technical-500 template rendering is incompatible with Python 3.14.
DEBUG_PROPAGATE_EXCEPTIONS = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "%(levelname)s %(name)s %(message)s"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "ERROR", "propagate": True},
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
}
