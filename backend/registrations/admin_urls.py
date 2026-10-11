from django.urls import path

from .views import (
    RegistrationDecisionView,
    RegistrationDetailView,
    RegistrationDocumentAccessView,
    RegistrationListView,
    RegistrationReportView,
    VerifyRegistrationDocumentView,
)

urlpatterns = [
    path("registrations/", RegistrationListView.as_view(), name="admin_registrations"),
    path(
        "registrations/<uuid:registration_id>/",
        RegistrationDetailView.as_view(),
        name="admin_registration_detail",
    ),
    path(
        "registrations/<uuid:registration_id>/decision/",
        RegistrationDecisionView.as_view(),
        name="admin_registration_decision",
    ),
    path(
        "registration-documents/<uuid:document_id>/file/",
        RegistrationDocumentAccessView.as_view(),
        name="admin_registration_document",
    ),
    path(
        "registration-documents/<uuid:document_id>/verification/",
        VerifyRegistrationDocumentView.as_view(),
        name="admin_registration_document_verification",
    ),
    path(
        "registration-reports/",
        RegistrationReportView.as_view(),
        name="admin_registration_reports",
    ),
]
