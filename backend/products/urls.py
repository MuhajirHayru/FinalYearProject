from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CategoryListView, FarmerListingViewSet, WholesalerListingViewSet

router = DefaultRouter()
router.register("farmer-listings", FarmerListingViewSet, basename="farmer-listings")
router.register(
    "wholesaler-listings", WholesalerListingViewSet, basename="wholesaler-listings"
)
router.register("categories", CategoryListView, basename="product-categories")

urlpatterns = [path("", include(router.urls))]
