from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import AuditLog, PlatformSettings, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("email", "full_name", "role", "status", "location", "created_at")
    list_filter = ("role", "status")
    search_fields = ("email", "full_name", "location")
    ordering = ("-created_at",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("full_name", "phone", "location", "latitude", "longitude")}),
        (
            "Permissions",
            {
                "fields": (
                    "role", "status", "rejection_reason", "privacy_policy_accepted",
                    "is_active", "is_staff", "is_superuser", "groups", "user_permissions",
                )
            },
        ),
        ("Dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (None, {"fields": ("email", "full_name", "password1", "password2")}),
    )


@admin.register(PlatformSettings)
class PlatformSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "registration_open", "require_approval", "maintenance_mode",
        "updated_by", "updated_at",
    )

    def has_add_permission(self, request):
        # Singleton row only (pk=1).
        return not PlatformSettings.objects.exists()


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "target")
    list_filter = ("action",)
    search_fields = ("target", "detail", "actor__full_name")
    readonly_fields = ("actor", "action", "target", "detail", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
