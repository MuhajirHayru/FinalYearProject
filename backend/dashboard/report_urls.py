from django.urls import path

from .report_views import (
    FinancialExportView,
    FinancialSummaryView,
    TransactionVolumeView,
)

urlpatterns = [
    path("financial-summary/", FinancialSummaryView.as_view(), name="financial_summary"),
    path(
        "financial-summary/export/",
        FinancialExportView.as_view(),
        name="financial_export",
    ),
    path("transaction-volume/", TransactionVolumeView.as_view(), name="transaction_volume"),
]
