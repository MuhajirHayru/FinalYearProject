from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import generics, response, views

from .models import Notification
from .serializers import NotificationSerializer


class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)


@extend_schema(responses=OpenApiTypes.OBJECT)
class UnreadCountView(views.APIView):
    def get(self, request):
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return response.Response({"success": True, "unread_count": count})


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
class MarkAllReadView(views.APIView):
    def post(self, request):
        updated = Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return response.Response({"success": True, "updated": updated})


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
class MarkReadView(views.APIView):
    def post(self, request, pk):
        updated = Notification.objects.filter(pk=pk, recipient=request.user).update(is_read=True)
        return response.Response({"success": True, "updated": updated})
