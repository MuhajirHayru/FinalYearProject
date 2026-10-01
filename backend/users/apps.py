from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "users"

    def ready(self):
        # Domain-event signal receivers (doc 4.11.2). Imported here so they are
        # active under every entry point: WSGI, ASGI and the test client.
        import greenpath.signals  # noqa: F401
