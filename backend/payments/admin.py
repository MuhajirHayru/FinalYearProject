from django.contrib import admin

from .models import Order, PaymentRecord


@admin.register(PaymentRecord)
class PaymentRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "submitted_by", "farmer", "product", "amount", "payment_method", "status", "submitted_at")
    list_filter = ("status", "payment_method")
    search_fields = ("reference_number", "submitted_by__full_name", "farmer__full_name")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("reference", "wholesaler", "farmer", "product", "total_amount", "status", "created_at")
    list_filter = ("status",)
