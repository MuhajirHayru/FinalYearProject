import logging

from django.conf import settings
from django.utils.module_loading import import_string


logger = logging.getLogger(__name__)


class VoiceTranscriptionError(Exception):
    """A configured transcription adapter could not safely transcribe audio."""


class VoiceTranscriptionUnavailable(VoiceTranscriptionError):
    """No usable transcription adapter is configured."""


def transcribe_voice(audio_file):
    configured = getattr(settings, "CHAT_VOICE_TRANSCRIBER", "")
    if not configured:
        raise VoiceTranscriptionUnavailable("No voice transcription adapter is configured.")

    try:
        adapter = import_string(configured) if isinstance(configured, str) else configured
    except (ImportError, AttributeError) as exc:
        logger.error("Voice transcription adapter could not be loaded.")
        raise VoiceTranscriptionUnavailable(
            "The configured voice transcription adapter is unavailable."
        ) from exc

    if not callable(adapter):
        raise VoiceTranscriptionUnavailable("The configured voice adapter is invalid.")

    try:
        transcript = adapter(
            audio_file.read(),
            content_type=getattr(audio_file, "content_type", ""),
        )
    except VoiceTranscriptionError:
        logger.warning("Voice transcription failed; message requires review.")
        raise
    except Exception as exc:
        logger.exception(
            "Voice transcription adapter raised an unexpected error; "
            "message requires review."
        )
        raise VoiceTranscriptionError(
            "The voice transcription adapter failed."
        ) from exc

    if not isinstance(transcript, str):
        raise VoiceTranscriptionError("The transcription adapter returned an invalid result.")
    return transcript
