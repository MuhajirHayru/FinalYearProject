from django.urls import path

from .views import (
    AnnouncementView,
    LoginView,
    LogoutView,
    MeView,
    RefreshView,
    RegisterView,
    UpdateProfileView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("token/refresh/", RefreshView.as_view(), name="token_refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("profile/", UpdateProfileView.as_view(), name="profile"),
    path("announcement/", AnnouncementView.as_view(), name="announcement"),
]
