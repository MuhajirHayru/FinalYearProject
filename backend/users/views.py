import logging
import smtplib
from urllib.error import URLError

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status, views
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.throttling import ScopedRateThrottle

from registrations.authentication import make_registration_token
from registrations.models import UserRegistration
from .authentication import password_token_version, token_matches_password
from .models import (
    AccountStatus,
    AuditLog,
    PlatformSettings,
    User,
    WebsiteContent,
    default_website_content,
)
from .recovery import RecoveryDeliveryError, send_password_reset
from .serializers import (
    LoginSerializer,
    LoginAttemptError,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ProfilePhotoSerializer,
    ProfileUpdateSerializer,
    UserSerializer,
)

logger = logging.getLogger(__name__)
REFRESH_COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 days, per NFR-04


def _issue_tokens(user):
    refresh = RefreshToken.for_user(user)
    refresh["pwdv"] = password_token_version(user)
    return str(refresh.access_token), str(refresh)


def _attach_refresh_cookie(response, refresh_token):
    response.set_cookie(
        settings.REFRESH_COOKIE_KEY,
        refresh_token,
        max_age=REFRESH_COOKIE_MAX_AGE,
        httponly=settings.REFRESH_COOKIE_HTTPONLY,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
        secure=settings.REFRESH_COOKIE_SECURE,
        path=settings.REFRESH_COOKIE_PATH,
    )
    return response


def _user_payload(user):
    return {
        "id": str(user.id),
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone,
        "profile_photo": user.profile_photo.url if user.profile_photo else "",
        "role": user.role,
        "role_display": user.get_role_display(),
        "status": user.status,
        "status_display": user.get_status_display(),
        "location": user.location,
        "permissions": user.get_role_permissions(),
        "financially_verified": user.financially_verified,
        "is_online": user.is_online,
    }


class RegisterView(generics.CreateAPIView):
    """POST /api/v1/auth/register/ — public registration (UC-01).

    Creates a PENDING account and notifies the User Admin queue (FR-F-01,
    FR-F-02).  Honours the Super Admin registration policy (FR-SA-04).
    """

    serializer_class = UserSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        config = PlatformSettings.load()
        if not config.registration_open:
            return Response(
                {"success": False, "error": "Registration is currently closed."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            user = serializer.save()
            UserRegistration.objects.create(user=user)
        return Response(
            {
                "success": True,
                "message": (
                    "Account created. Complete your role-specific registration "
                    "before it can be reviewed."
                ),
                "user": UserSerializer(user).data,
                "completion_token": make_registration_token(user),
            },
            status=status.HTTP_201_CREATED,
        )


class ResumeRegistrationView(views.APIView):
    """Exchange a pending account's password for a registration-only token."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        from django.core import signing
        from rest_framework import serializers
        from .models import Role

        class CredentialsSerializer(serializers.Serializer):
            email = serializers.EmailField()
            password = serializers.CharField(write_only=True)

        serializer = CredentialsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(email__iexact=serializer.validated_data["email"]).first()
        if (
            user is None
            or not user.check_password(serializer.validated_data["password"])
            or user.role not in (Role.FARMER, Role.WHOLESALER, Role.RETAILER)
        ):
            raise serializers.ValidationError("Invalid email or password.")
        try:
            registration = user.registration
        except UserRegistration.DoesNotExist:
            raise serializers.ValidationError("No incomplete registration was found.")
        if registration.status not in ("DRAFT", "CHANGES_REQUESTED", "REJECTED"):
            raise serializers.ValidationError("This registration is not available to edit.")
        if user.status not in (AccountStatus.PENDING, AccountStatus.REJECTED):
            raise serializers.ValidationError("This account is not awaiting registration.")
        return Response(
            {"success": True, "completion_token": make_registration_token(user)}
        )


@extend_schema(request=LoginSerializer, responses=OpenApiTypes.OBJECT)
class LoginView(views.APIView):
    """POST /api/v1/auth/login/ — access token in body, refresh in cookie.

    Mirrors the authentication flow in doc 5.1.6: the access token (1h) travels
    in the JSON body and the refresh token (7d) is set as an HttpOnly cookie.
    """

    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"
    serializer_class = LoginSerializer

    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        try:
            serializer.is_valid(raise_exception=True)
        except LoginAttemptError as exc:
            return Response(
                {
                    "success": False,
                    "error": str(exc.detail),
                    "attempts_remaining": exc.attempts_remaining,
                    "max_attempts": exc.max_attempts,
                    "locked_until": exc.locked_until,
                    "retry_after_seconds": exc.retry_after_seconds,
                },
                status=exc.status_code,
            )
        user = serializer.validated_data["user"]

        access, refresh = _issue_tokens(user)
        response = Response(
            {"success": True, "access": access, "user": _user_payload(user)}
        )
        return _attach_refresh_cookie(response, refresh)


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
class RefreshView(views.APIView):
    """POST /api/v1/auth/token/refresh/ — cookie-based silent refresh."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        token = request.COOKIES.get(settings.REFRESH_COOKIE_KEY)
        if not token:
            return Response(
                {"success": False, "error": "Refresh token missing."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            refresh = RefreshToken(token)
            user = User.objects.get(
                id=refresh.payload["user_id"], status=AccountStatus.APPROVED
            )
            if not token_matches_password(refresh, user):
                raise TokenError("Password changed after token issuance.")
        except (TokenError, User.DoesNotExist, KeyError):
            response = Response(
                {"success": False, "error": "Invalid or expired refresh token."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            response.delete_cookie(
                settings.REFRESH_COOKIE_KEY, path=settings.REFRESH_COOKIE_PATH
            )
            return response

        access, new_refresh = _issue_tokens(user)
        response = Response({"success": True, "access": access})
        return _attach_refresh_cookie(response, new_refresh)


class PasswordResetRequestView(views.APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset_request"

    @extend_schema(request=PasswordResetRequestSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        channel = serializer.validated_data["channel"]
        identifier = serializer.validated_data["identifier"]
        matches = (
            User.objects.filter(email__iexact=identifier)
            if channel == "email"
            else User.objects.filter(phone=identifier)
        )
        user = matches.first() if matches.count() == 1 else None

        if user is not None and (user.email if channel == "email" else user.phone):
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            reset_token = default_token_generator.make_token(user)
            reset_url = (
                f"{settings.FRONTEND_BASE_URL.rstrip('/')}/reset-password"
                f"?uid={uid}&token={reset_token}"
            )
            try:
                send_password_reset(user, channel, reset_url)
            except (
                RecoveryDeliveryError,
                ImproperlyConfigured,
                OSError,
                smtplib.SMTPException,
                TimeoutError,
                URLError,
            ) as exc:
                logger.error(
                    "Password reset delivery failed: channel=%s user_id=%s error=%s",
                    channel,
                    user.pk,
                    type(exc).__name__,
                )

        return Response(
            {
                "success": True,
                "message": (
                    "If an account matches those details, password reset "
                    "instructions will be sent."
                ),
            },
            status=status.HTTP_202_ACCEPTED,
        )


class PasswordResetConfirmView(views.APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset_confirm"

    @extend_schema(request=PasswordResetConfirmSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        candidate = serializer.validated_data["user"]

        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=candidate.pk)
            if not default_token_generator.check_token(
                user, serializer.validated_data["token"]
            ):
                return Response(
                    {
                        "success": False,
                        "error": "This password reset link is invalid or expired.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user.set_password(serializer.validated_data["new_password"])
            user.password_changed_at = timezone.now()
            user.failed_login_attempts = 0
            user.locked_until = None
            user.save(
                update_fields=[
                    "password",
                    "password_changed_at",
                    "failed_login_attempts",
                    "locked_until",
                    "updated_at",
                ]
            )
            AuditLog.objects.create(
                actor=None,
                action="password_reset_completed",
                target=str(user.pk),
                detail="Password reset completed.",
            )

        response = Response(
            {"success": True, "message": "Password updated. Please sign in again."}
        )
        response.delete_cookie(
            settings.REFRESH_COOKIE_KEY, path=settings.REFRESH_COOKIE_PATH
        )
        return response


class PasswordChangeView(views.APIView):
    @extend_schema(request=PasswordChangeSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = PasswordChangeSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            if not user.check_password(serializer.validated_data["current_password"]):
                return Response(
                    {"success": False, "error": "Current password is incorrect."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user.set_password(serializer.validated_data["new_password"])
            user.password_changed_at = timezone.now()
            user.failed_login_attempts = 0
            user.locked_until = None
            user.save(
                update_fields=[
                    "password",
                    "password_changed_at",
                    "failed_login_attempts",
                    "locked_until",
                    "updated_at",
                ]
            )
            AuditLog.objects.create(
                actor=user,
                action="password_changed",
                target=str(user.pk),
                detail="User changed their password.",
            )

        response = Response(
            {"success": True, "message": "Password updated. Please sign in again."}
        )
        response.delete_cookie(
            settings.REFRESH_COOKIE_KEY, path=settings.REFRESH_COOKIE_PATH
        )
        return response


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
class LogoutView(views.APIView):
    """POST /api/v1/auth/logout/ — clear the refresh cookie."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        response = Response({"success": True, "message": "Logged out."})
        response.delete_cookie(
            settings.REFRESH_COOKIE_KEY, path=settings.REFRESH_COOKIE_PATH
        )
        return response


@extend_schema(responses=OpenApiTypes.OBJECT)
class MeView(views.APIView):
    """GET /api/v1/auth/me/ — current profile, role and effective permissions."""

    def get(self, request):
        return Response(
            {
                "success": True,
                "user": UserSerializer(request.user).data,
                "permissions": request.user.get_role_permissions(),
            }
        )


@extend_schema(request=ProfileUpdateSerializer, responses=OpenApiTypes.OBJECT)
class UpdateProfileView(views.APIView):
    """PATCH /api/v1/auth/profile/ — self-service profile fields only."""

    def patch(self, request):
        serializer = ProfileUpdateSerializer(
            request.user, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"success": True, "user": UserSerializer(request.user).data})


class UpdateProfilePhotoView(views.APIView):
    """POST/DELETE /api/v1/auth/profile/photo/ — manage only the caller's image."""

    serializer_class = ProfilePhotoSerializer

    def post(self, request):
        serializer = ProfilePhotoSerializer(
            request.user,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        old_name = request.user.profile_photo.name
        user = serializer.save()
        if old_name and old_name != user.profile_photo.name:
            user.profile_photo.storage.delete(old_name)
        return Response({"success": True, "user": UserSerializer(user).data})

    def delete(self, request):
        user = request.user
        if user.profile_photo:
            user.profile_photo.delete(save=False)
            user.save(update_fields=["profile_photo", "updated_at"])
        return Response({"success": True, "user": UserSerializer(user).data})


@extend_schema(responses=OpenApiTypes.OBJECT)
class WebsiteContentView(views.APIView):
    """GET /api/v1/auth/website-content/ — public, database-backed site content."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        website = WebsiteContent.load()
        defaults = default_website_content()
        configured = website.content if isinstance(website.content, dict) else {}
        return Response(
            {
                "platform_name": website.platform_name or "Green Path",
                "logo_url": (
                    request.build_absolute_uri(website.logo.url)
                    if website.logo
                    else None
                ),
                "favicon_url": (
                    request.build_absolute_uri(website.favicon.url)
                    if website.favicon
                    else None
                ),
                "hero_image_url": (
                    request.build_absolute_uri(website.hero_image.url)
                    if website.hero_image
                    else None
                ),
                "content": {**defaults, **configured},
                "updated_at": website.updated_at,
                "updated_by": (
                    website.updated_by.full_name if website.updated_by else None
                ),
            }
        )


class AnnouncementView(views.APIView):
    """GET /api/v1/auth/announcement/ — platform banner (FR-SA-04)."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        config = PlatformSettings.load()
        return Response(
            {
                "success": True,
                "announcement": config.announcement,
                "registration_open": config.registration_open,
            }
        )
