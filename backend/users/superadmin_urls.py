from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .superadmin_views import (
    AdminAccountViewSet,
    AnnouncementBroadcastView,
    AuditLogListView,
    OverrideDecisionView,
    PlatformSettingsView,
    SuperAdminDataView,
    SystemHealthView,
)

router = DefaultRouter()
router.register("accounts", AdminAccountViewSet, basename="superadmin-accounts")
router.register("audit", AuditLogListView, basename="superadmin-audit")

urlpatterns = router.urls + [
    # FR-SA-01
    path("data/", SuperAdminDataView.as_view(), name="superadmin_data"),
    # FR-SA-03
    path("users/<uuid:pk>/override/", OverrideDecisionView.as_view(), name="superadmin_override"),
    # FR-SA-04
    path("settings/", PlatformSettingsView.as_view(), name="superadmin_settings"),
    path("announcement/", AnnouncementBroadcastView.as_view(), name="superadmin_announcement"),
    # FR-SA-05
    path("health/", SystemHealthView.as_view(), name="superadmin_health"),
]
