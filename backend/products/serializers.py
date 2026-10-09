from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Category, Product, UnitOfMeasure

MAX_PRODUCT_IMAGES = 8


class ProductSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.full_name", read_only=True)
    owner_location = serializers.CharField(source="owner.location", read_only=True)
    owner_role = serializers.CharField(source="owner.get_role_display", read_only=True)
    owner_profile_photo = serializers.ImageField(
        source="owner.profile_photo", read_only=True, allow_null=True
    )
    owner_financially_verified = serializers.BooleanField(
        source="owner.financially_verified", read_only=True
    )
    owner_is_online = serializers.BooleanField(source="owner.is_online", read_only=True)
    owner_latitude = serializers.DecimalField(
        source="owner.latitude", max_digits=9, decimal_places=6, read_only=True
    )
    owner_longitude = serializers.DecimalField(
        source="owner.longitude", max_digits=9, decimal_places=6, read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    category_display = serializers.CharField(source="get_category_display", read_only=True)
    unit_display = serializers.CharField(source="get_unit_of_measure_display", read_only=True)
    is_owner = serializers.SerializerMethodField()
    distance_km = serializers.SerializerMethodField()
    total_value = serializers.SerializerMethodField()
    owner_average_rating = serializers.SerializerMethodField()
    owner_review_count = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "title", "description", "category", "category_display",
            "quantity", "unit_of_measure", "unit_display", "price_per_unit",
            "status", "status_display", "product_type", "owner", "owner_name",
            "owner_location", "owner_role", "owner_profile_photo",
            "owner_financially_verified", "owner_is_online",
            "owner_latitude", "owner_longitude",
            "owner_average_rating", "owner_review_count",
            "images", "is_owner", "distance_km", "total_value",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "owner", "product_type", "images",
            "created_at", "updated_at",
        ]

    @extend_schema_field(serializers.BooleanField)
    def get_is_owner(self, obj):
        request = self.context.get("request")
        return bool(request and request.user and request.user == obj.owner)

    @extend_schema_field(serializers.FloatField(allow_null=True))
    def get_distance_km(self, obj):
        """Present only when the ORM annotated it (retailer proximity ranking)."""
        value = getattr(obj, "distance_km", None)
        return round(float(value), 2) if value is not None else None

    @extend_schema_field(serializers.CharField)
    def get_total_value(self, obj):
        return str(obj.total_value)

    @extend_schema_field(serializers.FloatField(allow_null=True))
    def get_owner_average_rating(self, obj):
        value = getattr(obj, "owner_average_rating", None)
        return round(float(value), 2) if value is not None else None

    @extend_schema_field(serializers.IntegerField())
    def get_owner_review_count(self, obj):
        return getattr(obj, "owner_review_count", 0)

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value

    def validate_price_per_unit(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than zero.")
        return value

    def validate_images(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("images must be a list of URLs.")
        if len(value) > MAX_PRODUCT_IMAGES:
            raise serializers.ValidationError("A listing may hold at most 8 images.")
        return value


class ProductCreateSerializer(serializers.ModelSerializer):
    """Farmer / Wholesaler listing creation (FR-F-04, FR-W-05)."""

    class Meta:
        model = Product
        fields = [
            "title", "description", "category", "quantity",
            "unit_of_measure", "price_per_unit", "images",
        ]

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value

    def validate_price_per_unit(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than zero.")
        return value

    def validate_images(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("images must be a list of URLs.")
        if len(value) > MAX_PRODUCT_IMAGES:
            raise serializers.ValidationError("A listing may hold at most 8 images.")
        return value


class ProductImageUploadSerializer(serializers.Serializer):
    """Multi-part image upload appended to a listing's ``images`` list."""

    image = serializers.ImageField(required=True)

    def validate_image(self, value):
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("Image must be 5 MB or smaller.")
        return value


class ProductImagesSerializer(serializers.Serializer):
    """Existing image references retained or reordered for a listing."""

    images = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=True,
        max_length=MAX_PRODUCT_IMAGES,
    )


class CategorySerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


def category_choices():
    return [{"value": value, "label": label} for value, label in Category.choices]


def unit_choices():
    return [{"value": value, "label": label} for value, label in UnitOfMeasure.choices]
