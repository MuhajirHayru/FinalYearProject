from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateRegistrationStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(
            location=getattr(
                settings,
                "REGISTRATION_PRIVATE_MEDIA_ROOT",
                settings.BASE_DIR / "private-media",
            ),
            base_url=None,
        )

    def url(self, name):
        raise ValueError("Private registration documents have no public URL.")
