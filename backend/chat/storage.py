from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateChatStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(
            location=getattr(
                settings,
                "CHAT_PRIVATE_MEDIA_ROOT",
                settings.BASE_DIR / "private-media" / "chat",
            ),
            base_url=None,
        )

    def url(self, name):
        raise ValueError("Private chat audio has no public URL.")
