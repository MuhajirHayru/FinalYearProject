from django.urls import path

from .views import (
    AdminDashboardView,
    FarmerDashboardView,
    FinancialOperationsSummaryView,
    PaymentSummaryView,
    RetailerDashboardView,
    WholesalerDashboardView,
)
from .wallet_report_views import WalletActivityExportView, WalletActivityReportView

urlpatterns = [
    path("farmer/", FarmerDashboardView.as_view(), name="dashboard_farmer"),
    path("wholesaler/", WholesalerDashboardView.as_view(), name="dashboard_wholesaler"),
    path("retailer/", RetailerDashboardView.as_view(), name="dashboard_retailer"),
    path("admin/", AdminDashboardView.as_view(), name="dashboard_admin"),
    path("payments/", PaymentSummaryView.as_view(), name="dashboard_payments"),
    path(
        "financial-operations/",
        FinancialOperationsSummaryView.as_view(),
        name="dashboard_financial_operations",
    ),
    path(
        "wallet-activity/",
        WalletActivityReportView.as_view(),
        name="dashboard_wallet_activity",
    ),
    path(
        "wallet-activity/export/",
        WalletActivityExportView.as_view(),
        name="dashboard_wallet_activity_export",
    ),
]
