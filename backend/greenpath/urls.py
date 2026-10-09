from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    # Auth routes live in users.urls: LoginView/RefreshView wrap SimpleJWT so the
    # refresh token is returned as an httpOnly cookie. Declaring them here first
    # would shadow those views (doc 5.1.5 / 3.7).
    path("api/v1/auth/", include("users.urls")),
    path("api/v1/products/", include("products.urls")),
    path("api/v1/chat/", include("chat.urls")),
    path("api/v1/payments/", include("payments.urls")),
    path("api/v1/orders/", include("payments.order_urls")),
    path("api/v1/admin/", include("users.admin_urls")),
    path("api/v1/superadmin/", include("users.superadmin_urls")),
    path("api/v1/notifications/", include("notifications.urls")),
    path("api/v1/dashboard/", include("dashboard.urls")),
    path("api/v1/reports/", include("dashboard.report_urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger"),
    path("api/v1/health/", lambda r: JsonResponse({"status": "ok"}), name="health"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
