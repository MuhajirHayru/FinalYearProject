from django.urls import path

from .views import (
    LocationOptionsView,
    ProductTypeOptionsView,
    RegistrationDocumentView,
    RegistrationDraftView,
    SubmitRegistrationView,
)

urlpatterns = [
    path("locations/", LocationOptionsView.as_view(), name="registration_locations"),
    path("product-types/", ProductTypeOptionsView.as_view(), name="registration_product_types"),
    path("me/", RegistrationDraftView.as_view(), name="registration_me"),
    path("me/submit/", SubmitRegistrationView.as_view(), name="registration_submit"),
    path("me/documents/", RegistrationDocumentView.as_view(), name="registration_documents"),
    path(
        "me/documents/<uuid:document_id>/",
        RegistrationDocumentView.as_view(),
        name="registration_document_detail",
    ),
]
