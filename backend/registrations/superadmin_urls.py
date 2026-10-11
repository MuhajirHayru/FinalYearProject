from django.urls import path

from .views import AdministratorScopeDetailView, AdministratorScopeListCreateView

urlpatterns = [
    path("admin-scopes/", AdministratorScopeListCreateView.as_view(), name="admin_scopes"),
    path(
        "admin-scopes/<uuid:user_id>/",
        AdministratorScopeDetailView.as_view(),
        name="admin_scope_detail",
    ),
]
