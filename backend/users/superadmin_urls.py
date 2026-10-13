from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .superadmin_views import (
    AdminAccountViewSet,
    AnnouncementBroadcastView,
    AuditLogListView,
    LoginUnlockView,
    OverrideDecisionView,
    PlatformSettingsView,
    SuperAdminDataView,
    SuperAdminUsersListView,
    SystemHealthView,
    WebsiteContentAdminView,
)

router = DefaultRouter()
router.register("accounts", AdminAccountViewSet, basename="superadmin-accounts")
router.register("audit", AuditLogListView, basename="superadmin-audit")

urlpatterns = router.urls + [
    # FR-SA-01
    path("data/", SuperAdminDataView.as_view(), name="superadmin_data"),
    path("users/", SuperAdminUsersListView.as_view(), name="superadmin_users"),
    # FR-SA-03
    path("users/<uuid:pk>/override/", OverrideDecisionView.as_view(), name="superadmin_override"),
    path(
        "users/<uuid:pk>/unlock-login/",
        LoginUnlockView.as_view(),
        name="superadmin_unlock_login",
    ),
    # FR-SA-04
    path("settings/", PlatformSettingsView.as_view(), name="superadmin_settings"),
    path(
        "website-content/",
        WebsiteContentAdminView.as_view(),
        name="superadmin_website_content",
    ),
    path("announcement/", AnnouncementBroadcastView.as_view(), name="superadmin_announcement"),
    # FR-SA-05
    path("health/", SystemHealthView.as_view(), name="superadmin_health"),
]
