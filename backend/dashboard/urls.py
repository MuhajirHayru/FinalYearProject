from django.urls import path

from .views import (
    AdminDashboardView,
    FarmerDashboardView,
    PaymentSummaryView,
    RetailerDashboardView,
    WholesalerDashboardView,
)

urlpatterns = [
    path("farmer/", FarmerDashboardView.as_view(), name="dashboard_farmer"),
    path("wholesaler/", WholesalerDashboardView.as_view(), name="dashboard_wholesaler"),
    path("retailer/", RetailerDashboardView.as_view(), name="dashboard_retailer"),
    path("admin/", AdminDashboardView.as_view(), name="dashboard_admin"),
    path("payments/", PaymentSummaryView.as_view(), name="dashboard_payments"),
]
