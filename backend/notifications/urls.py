from django.urls import path

from .views import MarkAllReadView, MarkReadView, NotificationListView, UnreadCountView

urlpatterns = [
    path("", NotificationListView.as_view(), name="notifications"),
    path("unread-count/", UnreadCountView.as_view(), name="notification_unread_count"),
    path("mark-all-read/", MarkAllReadView.as_view(), name="notifications_mark_all"),
    path("<uuid:pk>/mark-read/", MarkReadView.as_view(), name="notifications_mark_read"),
]
