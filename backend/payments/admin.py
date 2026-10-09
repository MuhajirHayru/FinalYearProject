from django.contrib import admin

from .models import BankAccount, Order, PaymentRecord, PayoutBank


@admin.register(PaymentRecord)
class PaymentRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "submitted_by", "farmer", "product", "amount", "payment_method", "status", "submitted_at")
    list_filter = ("status", "payment_method")
    search_fields = ("reference_number", "submitted_by__full_name", "farmer__full_name")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("reference", "wholesaler", "farmer", "product", "total_amount", "status", "created_at")
    list_filter = ("status",)


@admin.register(PayoutBank)
class PayoutBankAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code")


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ("user", "bank", "account_holder_name", "account_number_last4", "status", "is_default")
    list_filter = ("bank", "status", "is_default")
    search_fields = ("user__full_name", "user__email", "account_holder_name")
    readonly_fields = (
        "account_number_encrypted", "account_number_last4", "status",
        "created_at", "updated_at",
    )
