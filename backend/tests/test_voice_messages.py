import os

from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings

from chat.models import Message, MessageKind, MessageModerationStatus
from notifications.models import Notification
from users.models import PlatformSettings


def successful_transcriber(audio_bytes, *, content_type):
    assert audio_bytes
    assert content_type == "audio/webm"
    return "Can you supply 500 kg of tomatoes?"


def restricted_transcriber(audio_bytes, *, content_type):
    assert audio_bytes
    return "Call me at +251 911 234 567."


def failing_transcriber(audio_bytes, *, content_type):
    assert audio_bytes
    raise RuntimeError("transcription service unavailable")


def voice_file():
    return SimpleUploadedFile(
        "recording.webm",
        b"\x1a\x45\xdf\xa3test audio data",
        content_type="audio/webm",
    )


def post_voice(api, channel, audio=None):
    return api.post(
        f"/api/v1/chat/channels/{channel.pk}/messages/",
        {"kind": "VOICE", "audio": audio or voice_file()},
        format="multipart",
    )


def test_missing_transcriber_keeps_voice_pending_and_private(
    api, chat_channel, farmer, wholesaler
):
    api.force_authenticate(user=farmer)

    response = post_voice(api, chat_channel)

    assert response.status_code == 202, response.data
    message = Message.objects.get(channel=chat_channel)
    assert message.kind == MessageKind.VOICE
    assert message.moderation_status == MessageModerationStatus.PENDING_REVIEW
    assert message.content == ""
    assert "recording.webm" not in message.audio_file.name
    assert str(message.audio_file.path).startswith(str(settings.CHAT_PRIVATE_MEDIA_ROOT))
    assert not Notification.objects.filter(recipient=wholesaler, type="MESSAGE").exists()

    sender_history = api.get(
        f"/api/v1/chat/channels/{chat_channel.pk}/messages/"
    )
    assert sender_history.data["results"][0]["moderation_status"] == "PENDING_REVIEW"

    api.force_authenticate(user=wholesaler)
    recipient_history = api.get(
        f"/api/v1/chat/channels/{chat_channel.pk}/messages/"
    )
    assert recipient_history.data["results"] == []
    audio_response = api.get(response.data["message"]["audio_url"])
    assert audio_response.status_code == 404


def test_transcriber_error_keeps_voice_pending_and_private(
    api, chat_channel, farmer, wholesaler
):
    from django.test import override_settings

    with override_settings(CHAT_VOICE_TRANSCRIBER=failing_transcriber):
        api.force_authenticate(user=farmer)
        response = post_voice(api, chat_channel)

    assert response.status_code == 202, response.data
    message = Message.objects.get(channel=chat_channel)
    assert message.moderation_status == MessageModerationStatus.PENDING_REVIEW
    assert not Notification.objects.filter(
        recipient=wholesaler, type="MESSAGE"
    ).exists()


def test_transcribed_contact_details_block_voice_before_delivery(
    api, chat_channel, farmer
):
    from django.test import override_settings

    with override_settings(CHAT_VOICE_TRANSCRIBER=restricted_transcriber):
        api.force_authenticate(user=farmer)
        response = post_voice(api, chat_channel)

    assert response.status_code == 400, response.data
    assert "restricted contact or location" in str(response.data).lower()
    assert not Message.objects.filter(channel=chat_channel).exists()


def test_approved_voice_is_accessible_only_to_channel_participants(
    api, chat_channel, farmer, wholesaler, farmer_b
):
    from django.test import override_settings

    with override_settings(CHAT_VOICE_TRANSCRIBER=successful_transcriber):
        api.force_authenticate(user=farmer)
        response = post_voice(api, chat_channel)

    assert response.status_code == 201, response.data
    message = Message.objects.get(channel=chat_channel)
    assert message.moderation_status == MessageModerationStatus.APPROVED
    assert message.content == ""
    assert response.data["message"]["audio_url"]
    assert Notification.objects.filter(recipient=wholesaler, type="MESSAGE").exists()

    api.force_authenticate(user=wholesaler)
    audio_response = api.get(response.data["message"]["audio_url"])
    assert audio_response.status_code == 200
    assert audio_response["Cache-Control"] == "private, no-store"
    assert b"".join(audio_response.streaming_content) == (
        b"\x1a\x45\xdf\xa3test audio data"
    )

    api.force_authenticate(user=farmer_b)
    outsider_response = api.get(response.data["message"]["audio_url"])
    assert outsider_response.status_code == 404


def test_moderator_can_review_pending_voice_once(
    api, chat_channel, farmer, financial_manager, wholesaler
):
    api.force_authenticate(user=farmer)
    submitted = post_voice(api, chat_channel)
    message_id = submitted.data["message"]["id"]

    api.force_authenticate(user=financial_manager)
    queue = api.get("/api/v1/chat/voice-moderation/")
    assert queue.status_code == 200, queue.data
    assert [item["id"] for item in queue.data["results"]] == [message_id]
    audio_response = api.get(queue.data["results"][0]["audio_url"])
    assert audio_response.status_code == 200
    assert b"".join(audio_response.streaming_content) == (
        b"\x1a\x45\xdf\xa3test audio data"
    )

    reviewed = api.post(
        f"/api/v1/chat/voice-moderation/{message_id}/review/",
        {"decision": "APPROVE", "reason": "Reviewed for restricted information"},
        format="json",
    )
    assert reviewed.status_code == 200, reviewed.data
    assert reviewed.data["message"]["moderation_status"] == "APPROVED"
    assert Notification.objects.filter(
        recipient=wholesaler,
        message__contains="passed moderation",
    ).exists()

    duplicate = api.post(
        f"/api/v1/chat/voice-moderation/{message_id}/review/",
        {"decision": "APPROVE", "reason": "Duplicate attempt"},
        format="json",
    )
    assert duplicate.status_code == 400


def test_blocked_voice_is_deleted_after_moderation(
    api,
    chat_channel,
    farmer,
    financial_manager,
    django_capture_on_commit_callbacks,
):
    api.force_authenticate(user=farmer)
    submitted = post_voice(api, chat_channel)
    message = Message.objects.get(pk=submitted.data["message"]["id"])
    audio_path = message.audio_file.path

    api.force_authenticate(user=financial_manager)
    with django_capture_on_commit_callbacks(execute=True):
        reviewed = api.post(
            f"/api/v1/chat/voice-moderation/{message.pk}/review/",
            {"decision": "BLOCK", "reason": "Contains private contact information"},
            format="json",
        )

    assert reviewed.status_code == 200, reviewed.data
    message.refresh_from_db()
    assert message.moderation_status == MessageModerationStatus.BLOCKED
    assert not message.audio_file
    assert not os.path.exists(audio_path)


def test_voice_audio_route_requires_authentication(api, chat_channel, farmer):
    from django.test import override_settings

    with override_settings(CHAT_VOICE_TRANSCRIBER=successful_transcriber):
        api.force_authenticate(user=farmer)
        response = post_voice(api, chat_channel)
    url = response.data["message"]["audio_url"]
    api.force_authenticate(user=None)
    unauthorized = api.get(url)
    assert unauthorized.status_code == 401


def test_voice_message_requires_microphone_capable_audio_file(api, chat_channel, farmer):
    api.force_authenticate(user=farmer)
    invalid = SimpleUploadedFile(
        "recording.txt", b"not audio", content_type="text/plain"
    )

    response = post_voice(api, chat_channel, invalid)

    assert response.status_code == 400
    assert not Message.objects.filter(channel=chat_channel).exists()


def test_voice_messages_can_be_disabled_by_super_admin_policy(
    api, chat_channel, farmer
):
    policy = PlatformSettings.load()
    policy.voice_messaging_enabled = False
    policy.save(update_fields=["voice_messaging_enabled"])

    api.force_authenticate(user=farmer)
    response = post_voice(api, chat_channel)

    assert response.status_code == 403
    assert "temporarily unavailable" in str(response.data).lower()
    assert not Message.objects.filter(channel=chat_channel).exists()
