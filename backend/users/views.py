from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status, views
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .models import AccountStatus, PlatformSettings, User
from .serializers import LoginSerializer, ProfileUpdateSerializer, UserSerializer

REFRESH_COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 days, per NFR-04


def _issue_tokens(user):
    refresh = RefreshToken.for_user(user)
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
        "role": user.role,
        "role_display": user.get_role_display(),
        "status": user.status,
        "status_display": user.get_status_display(),
        "location": user.location,
        "permissions": user.get_role_permissions(),
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
        user = serializer.save()

        if not config.require_approval:
            user.approve()
            return Response(
                {
                    "success": True,
                    "message": "Registration successful. Your account is active.",
                    "user": UserSerializer(user).data,
                },
                status=status.HTTP_201_CREATED,
            )

        # The approval-queue notification is emitted by the user_registered
        # domain event (doc 4.11.2), so the view does not call notify().
        return Response(
            {
                "success": True,
                "message": (
                    "Registration submitted. Your account is pending admin approval."
                ),
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema(request=LoginSerializer, responses=OpenApiTypes.OBJECT)
class LoginView(views.APIView):
    """POST /api/v1/auth/login/ — access token in body, refresh in cookie.

    Mirrors the authentication flow in doc 5.1.6: the access token (1h) travels
    in the JSON body and the refresh token (7d) is set as an HttpOnly cookie.
    """

    permission_classes = [permissions.AllowAny]
    serializer_class = LoginSerializer

    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
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
        except Exception:
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


@extend_schema(responses=OpenApiTypes.OBJECT)
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
