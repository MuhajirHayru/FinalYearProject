from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from greenpath.realtime import push_chat_event
from products.models import Product
from users.models import Role, User
from users.permissions import CanStartConversation, IsChatParticipant

from .models import ChatChannel, Message
from .serializers import ChatChannelSerializer, MessageSerializer

# ---------------------------------------------------------------------------
# FR-F-08 / FR-W-06 / FR-R-04: who may talk to whom.
# Farmers may only reach verified wholesalers and administrators; they may not
# contact retailers directly.
# ---------------------------------------------------------------------------
ALLOWED_COUNTERPARTIES = {
    Role.FARMER: {
        Role.WHOLESALER,
        Role.USER_ADMIN,
        Role.FINANCIAL_MANAGER,
        Role.SUPER_ADMIN,
    },
    Role.WHOLESALER: {
        Role.FARMER,
        Role.RETAILER,
        Role.USER_ADMIN,
        Role.FINANCIAL_MANAGER,
        Role.SUPER_ADMIN,
    },
    Role.RETAILER: {
        Role.WHOLESALER,
        Role.USER_ADMIN,
        Role.SUPER_ADMIN,
    },
    Role.USER_ADMIN: {
        Role.FARMER,
        Role.WHOLESALER,
        Role.RETAILER,
        Role.FINANCIAL_MANAGER,
        Role.SUPER_ADMIN,
    },
    Role.FINANCIAL_MANAGER: {
        Role.FARMER,
        Role.WHOLESALER,
        Role.USER_ADMIN,
        Role.SUPER_ADMIN,
    },
    Role.SUPER_ADMIN: set(Role.values),
}


def can_communicate(actor, other):
    """Return True when ``actor`` is permitted to open a channel with ``other``."""
    if not actor or not other or actor == other:
        return False
    return other.role in ALLOWED_COUNTERPARTIES.get(actor.role, set())


class ChatChannelViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """GET/POST /api/v1/chat/channels/ — the requester's active conversations."""

    serializer_class = ChatChannelSerializer
    queryset = ChatChannel.objects.none()  # only for schema lookup-type inference

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated(), CanStartConversation()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return (
            ChatChannel.objects.filter(participants=self.request.user)
            .prefetch_related("participants")
            .distinct()
        )

    def create(self, request, *args, **kwargs):
        participant_ids = request.data.get("participant_ids") or request.data.get(
            "participants"
        )
        if not participant_ids:
            return Response(
                {"success": False, "error": "A participant is required."},
                status=400,
            )
        if not isinstance(participant_ids, (list, tuple)):
            return Response(
                {"success": False, "error": "participant_ids must be a list."},
                status=400,
            )

        other = User.objects.filter(id__in=list(participant_ids)).first()
        if other is None:
            return Response(
                {"success": False, "error": "A valid participant is required."},
                status=400,
            )
        if not can_communicate(request.user, other):
            return Response(
                {
                    "success": False,
                    "error": "Your role is not allowed to communicate with this user.",
                },
                status=403,
            )

        product = None
        product_id = request.data.get("related_product")
        if product_id:
            product = Product.objects.filter(id=product_id).first()

        channel = (
            ChatChannel.objects.filter(participants=request.user)
            .filter(participants=other)
            .first()
        )
        if channel is None:
            channel = ChatChannel.objects.create(related_product=product)
            channel.participants.add(request.user, other)
        elif product and channel.related_product_id is None:
            channel.related_product = product
            channel.save(update_fields=["related_product"])

        return Response(
            {
                "success": True,
                "channel": ChatChannelSerializer(
                    channel, context={"request": request}
                ).data,
            },
            status=201,
        )


class ChannelMessagesViewSet(
    mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet
):
    """GET/POST /api/v1/chat/channels/{channelID}/messages/ — message history."""

    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]

    def get_channel(self):
        """Return the addressed channel, or 404 when the caller is not a member.

        ``IsChatParticipant`` cannot be relied on here: a DRF list route never
        calls ``get_object()``, so object permissions would silently be skipped
        and a non-member could post into someone else's conversation.
        """
        channel = (
            ChatChannel.objects.filter(
                id=self.kwargs.get("channel_pk"), participants=self.request.user
            )
            .prefetch_related("participants")
            .first()
        )
        if channel is None:
            raise NotFound("Channel not found.")
        return channel

    def get_queryset(self):
        return (
            Message.objects.filter(
                channel=self.get_channel(),
            )
            .select_related("sender")
            .order_by("sent_at")
        )

    def create(self, request, *args, **kwargs):
        channel = self.get_channel()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = serializer.save(sender=request.user, channel=channel)

        channel.last_message_at = message.sent_at
        channel.save(update_fields=["last_message_at"])

        # Participant notifications come from the message_received domain event
        # (doc 4.11.2); the view only fans the message out over the socket.
        push_chat_event(
            str(channel.id),
            {
                "type": "chat.message",
                "channel_id": str(channel.id),
                "message": MessageSerializer(message).data,
            },
        )
        return Response(
            {"success": True, "message": MessageSerializer(message).data},
            status=201,
        )


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
class MarkChannelReadView(viewsets.ViewSet):
    """POST /api/v1/chat/channels/{channelID}/mark-read/"""

    permission_classes = [IsAuthenticated]

    def create(self, request, channel_pk=None):
        if not ChatChannel.objects.filter(
            id=channel_pk, participants=request.user
        ).exists():
            return Response({"success": False, "error": "Channel not found."}, status=404)
        updated = Message.objects.filter(
            channel_id=channel_pk,
        ).exclude(sender=request.user).update(is_read=True)
        return Response({"success": True, "updated": updated})
