from rest_framework import serializers

from .models import AssistantConversation, AssistantMessage


class AssistantConversationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssistantConversation
        fields = ("id", "title", "language", "created_at", "updated_at")
        read_only_fields = ("id", "title", "created_at", "updated_at")


class AssistantMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssistantMessage
        fields = ("id", "role", "content", "created_at")
        read_only_fields = fields


class AssistantSendMessageSerializer(serializers.Serializer):
    content = serializers.CharField(max_length=2000, trim_whitespace=True)
    language = serializers.ChoiceField(
        choices=AssistantConversation.Language.choices, required=False
    )

    def validate_content(self, value):
        if not value:
            raise serializers.ValidationError("Enter a message before sending.")
        return value
