from django.urls import path

from .views import (
    AnnouncementView,
    LoginView,
    LogoutView,
    MeView,
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RefreshView,
    RegisterView,
    ResumeRegistrationView,
    UpdateProfilePhotoView,
    UpdateProfileView,
    WebsiteContentView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("registration/resume/", ResumeRegistrationView.as_view(), name="registration_resume"),
    path("login/", LoginView.as_view(), name="login"),
    path("password-reset/request/", PasswordResetRequestView.as_view(), name="password_reset_request"),
    path("password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("password/change/", PasswordChangeView.as_view(), name="password_change"),
    path("token/refresh/", RefreshView.as_view(), name="token_refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("profile/", UpdateProfileView.as_view(), name="profile"),
    path("profile/photo/", UpdateProfilePhotoView.as_view(), name="profile_photo"),
    path("announcement/", AnnouncementView.as_view(), name="announcement"),
    path("website-content/", WebsiteContentView.as_view(), name="website_content"),
]
