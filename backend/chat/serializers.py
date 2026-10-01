from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from users.models import User
from users.serializers import PublicUserSerializer

from .models import ChatChannel, Message


class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source="sender.full_name", read_only=True)

    class Meta:
        model = Message
        fields = ["id", "channel", "sender", "sender_name", "content", "sent_at", "is_read"]
        # The channel comes from the nested route and the sender from the request
        # user, so neither may be supplied by the client.
        read_only_fields = ["id", "channel", "sender", "sent_at", "is_read"]


class ChatChannelSerializer(serializers.ModelSerializer):
    participants = PublicUserSerializer(many=True, read_only=True)
    participant_ids = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        many=True,
        write_only=True,
        source="participants",
        required=False,
    )
    related_product_title = serializers.CharField(
        source="related_product.title", read_only=True, default=None
    )
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = ChatChannel
        fields = [
            "id", "participants", "participant_ids", "related_product",
            "related_product_title", "last_message_at", "created_at",
            "last_message", "unread_count",
        ]
        read_only_fields = ["id", "last_message_at", "created_at"]

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_last_message(self, obj):
        msg = obj.messages.order_by("-sent_at").first()
        if not msg:
            return None
        return {"content": msg.content, "sender_name": msg.sender.full_name, "sent_at": msg.sent_at}

    @extend_schema_field(serializers.IntegerField)
    def get_unread_count(self, obj):
        request = self.context.get("request")
        if not request:
            return 0
        return obj.get_unread_count(request.user)
