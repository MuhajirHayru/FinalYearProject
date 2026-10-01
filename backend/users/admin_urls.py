from django.urls import path

from .admin_views import (
    AllUsersView,
    ApproveUserView,
    BroadcastMessageView,
    PendingUsersView,
    RejectUserView,
    SuspendUserView,
)

urlpatterns = [
    # FR-UA-01
    path("pending-users/", PendingUsersView.as_view(), name="admin_pending_users"),
    # FR-UA-03
    path("users/", AllUsersView.as_view(), name="admin_all_users"),
    # FR-UA-02
    path("users/<uuid:pk>/approve/", ApproveUserView.as_view(), name="admin_approve_user"),
    path("users/<uuid:pk>/reject/", RejectUserView.as_view(), name="admin_reject_user"),
    # FR-UA-03
    path("users/<uuid:pk>/suspend/", SuspendUserView.as_view(), name="admin_suspend_user"),
    # FR-UA-04
    path("messages/", BroadcastMessageView.as_view(), name="admin_broadcast"),
]
