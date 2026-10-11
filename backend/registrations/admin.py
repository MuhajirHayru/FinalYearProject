from django.contrib import admin

from .models import (
    AdministrativeLocation,
    AdministratorScope,
    AgriculturalProductType,
    RegistrationDocument,
    RegistrationReview,
    UserRegistration,
)


@admin.register(AdministrativeLocation)
class AdministrativeLocationAdmin(admin.ModelAdmin):
    list_display = ("name", "level", "parent", "source_id", "active")
    list_filter = ("level", "active")
    search_fields = ("name", "source_id")


@admin.register(AgriculturalProductType)
class AgriculturalProductTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "code", "active")
    list_filter = ("category", "active")
    search_fields = ("name", "code")


@admin.register(UserRegistration)
class UserRegistrationAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "location", "submitted_at")
    list_filter = ("status",)
    search_fields = ("user__full_name", "user__email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(RegistrationDocument)
class RegistrationDocumentAdmin(admin.ModelAdmin):
    list_display = ("registration", "document_type", "verification_status", "uploaded_at")
    list_filter = ("verification_status", "document_type")
    search_fields = ("registration__user__full_name", "original_filename")
    readonly_fields = ("file", "uploaded_at", "verified_at")


@admin.register(RegistrationReview)
class RegistrationReviewAdmin(admin.ModelAdmin):
    list_display = ("registration", "reviewer", "action", "created_at")
    list_filter = ("action",)
    readonly_fields = ("registration", "reviewer", "action", "reason", "created_at")


@admin.register(AdministratorScope)
class AdministratorScopeAdmin(admin.ModelAdmin):
    list_display = ("user", "level", "location")
    list_filter = ("level",)
    search_fields = ("user__full_name", "user__email", "location__name")
