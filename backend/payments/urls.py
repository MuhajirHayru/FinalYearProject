from rest_framework.routers import DefaultRouter

from .views import PaymentViewSet

router = DefaultRouter()
# PATCH /api/v1/payments/{id}/verify/  (FR-FM-02)
# PATCH /api/v1/payments/{id}/flag/
# PATCH /api/v1/payments/{id}/dispute/
# GET   /api/v1/payments/{id}/receipt/
router.register("", PaymentViewSet, basename="payments")

urlpatterns = router.urls
