from django.contrib import admin

from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "product_type", "category", "quantity", "price_per_unit", "status", "created_at")
    list_filter = ("product_type", "status", "category")
    search_fields = ("title", "owner__full_name")
