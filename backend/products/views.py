"""Product module endpoints (doc 5.1.5, FR-F-04/05, FR-W-02/05, FR-R-02/03).

Two logically separate resources share one table:

* ``/api/v1/products/farmer-listings/``  — created by Farmers, browsed by Wholesalers.
* ``/api/v1/products/wholesaler-listings/`` — created by Wholesalers from purchased
  stock, browsed by Retailers with proximity ranking.
"""
import os
import uuid

from django.conf import settings
from django.db.models import Q
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response

from users.models import AccountStatus, Role
from users.permissions import (
    IsAuthenticatedRole,
    IsFarmer,
    IsListingReaderOrOwner,
    IsOwnerOrAdmin,
    IsWholesaler,
)

from .geo import annotate_distance_km
from .models import Product, ProductStatus, ProductType
from .serializers import (
    MAX_PRODUCT_IMAGES,
    ProductCreateSerializer,
    ProductImagesSerializer,
    ProductImageUploadSerializer,
    ProductSerializer,
    category_choices,
    unit_choices,
)

ORDERING_FIELDS = {
    "created_at", "-created_at", "price_per_unit", "-price_per_unit",
    "title", "-title", "quantity", "-quantity",
}

# Who may browse which marketplace (doc 5.1.5 "Role Required" column).
FARMER_LISTING_READERS = (Role.WHOLESALER, Role.USER_ADMIN, Role.SUPER_ADMIN)
WHOLESALER_LISTING_READERS = (Role.RETAILER, Role.WHOLESALER, Role.USER_ADMIN)


class _BaseListingViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    parser_classes = [JSONParser, FormParser, MultiPartParser]
    owner_field = "owner"

    #: Listing type this viewset manages; set by subclasses.
    listing_type = None
    #: Roles allowed to create a listing.
    creator_roles: tuple = ()
    #: Roles allowed to browse another party's listings.
    reader_roles: tuple = ()

    def get_queryset(self):
        user = self.request.user
        qs = (
            Product.objects.filter(product_type=self.listing_type)
            .select_related("owner")
        )

        if self._own_listings_requested():
            qs = qs.filter(owner=user)
        else:
            qs = qs.visible_to(user)

        qs = self._apply_filters(qs)
        return self._apply_proximity(qs, user)

    # -- request parsing --------------------------------------------------
    def _own_listings_requested(self):
        return (
            self.action in ("my", "mine")
            or self.request.query_params.get("mine") == "1"
        )

    def _apply_filters(self, qs):
        params = self.request.query_params

        search = (params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(title__icontains=search) | Q(description__icontains=search)
            )

        category = params.get("category")
        if category and category != "ALL":
            qs = qs.filter(category=category)

        location = (params.get("location") or "").strip()
        if location:
            qs = qs.filter(owner__location__icontains=location)

        status_param = params.get("status")
        if status_param and status_param != "ALL":
            qs = qs.filter(status=status_param)

        unit = params.get("unit_of_measure")
        if unit and unit != "ALL":
            qs = qs.filter(unit_of_measure=unit)

        min_price = params.get("min_price")
        if min_price:
            try:
                qs = qs.filter(price_per_unit__gte=min_price)
            except (TypeError, ValueError):
                raise ValidationError({"min_price": "Must be a number."})

        max_price = params.get("max_price")
        if max_price:
            try:
                qs = qs.filter(price_per_unit__lte=max_price)
            except (TypeError, ValueError):
                raise ValidationError({"max_price": "Must be a number."})

        in_stock = params.get("in_stock")
        if in_stock == "1":
            qs = qs.filter(quantity__gt=0)

        ordering = params.get("ordering", "-created_at")
        if ordering in ORDERING_FIELDS:
            qs = qs.order_by(ordering)
        return qs

    def _apply_proximity(self, qs, user):
        """FR-R-02: retailer discovery ranked by geographic proximity.

        Opt-in through ``near_me=1`` (or ``ordering=distance_km``) so plain
        wholesaler browsing keeps its recency default.  Supplying ``radius_km``
        implies ``near_me=1`` — a radius without a centre is meaningless.
        """
        params = self.request.query_params
        radius_raw = params.get("radius_km")
        wants_proximity = (
            params.get("near_me") == "1"
            or params.get("ordering") == "distance_km"
            or bool(radius_raw)
        )
        if not wants_proximity or self._own_listings_requested():
            return qs

        radius = None
        if radius_raw:
            try:
                radius = float(radius_raw)
            except (TypeError, ValueError):
                raise ValidationError({"radius_km": "Must be a number."})

        annotated, has_origin = annotate_distance_km(qs, user)
        if not has_origin:
            # The caller explicitly asked to search by location but has no
            # coordinates on file: fail loudly instead of silently returning
            # an unfiltered, unranked list.
            raise ValidationError(
                {
                    "near_me": "Set your latitude and longitude to search by distance."
                }
            )

        annotated = annotated.order_by("distance_km", "-created_at")
        if radius is not None:
            annotated = annotated.filter(distance_km__lte=radius)
        return annotated

    # -- permissions ------------------------------------------------------
    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy",
                           "upload_image", "activate", "deactivate", "mark_sold"):
            return [IsOwnerOrAdmin()]
        if self.action == "retrieve":
            # A seller must reach the detail page of their own listing even when
            # the row is not publicly visible; everyone else still needs a
            # reader role from doc 5.1.5.
            return [
                IsListingReaderOrOwner(
                    reader_roles=self.reader_roles,
                    creator_roles=self.creator_roles,
                )
            ]
        if self.action in ("list", "my"):
            return [IsAuthenticatedRole(self.reader_roles)]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.action == "create":
            return ProductCreateSerializer
        if self.action == "upload_image":
            return ProductImageUploadSerializer
        return ProductSerializer

    # -- object level guards ---------------------------------------------
    def _assert_can_modify(self, instance):
        if instance.owner != self.request.user:
            raise PermissionDenied("You can only modify your own listings.")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user, product_type=self.listing_type)

    def create(self, request, *args, **kwargs):
        """Create the listing and echo the full representation.

        ``ProductCreateSerializer`` only carries writable input fields, so the
        default response would omit ``id``/``status`` — both of which the client
        needs immediately (e.g. to upload an image to the new listing).
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        body = ProductSerializer(
            serializer.instance, context=self.get_serializer_context()
        ).data
        return Response(
            body, status=status.HTTP_201_CREATED, headers=self.get_success_headers(body)
        )

    def perform_update(self, serializer):
        self._assert_can_modify(serializer.instance)
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        # Soft delete keeps historical payment/order references intact (PROTECT).
        instance = self.get_object()
        self._assert_can_modify(instance)
        instance.mark_deleted()
        return Response(
            {"success": True, "message": f"{instance.title} deleted."}, status=200
        )

    def perform_destroy(self, instance):
        self._assert_can_modify(instance)
        instance.mark_deleted()

    # -- extra actions ----------------------------------------------------
    @action(detail=False, methods=["get"])
    def my(self, request):
        """GET .../my/ — the caller's own listings, all statuses (TC-BE-15)."""
        queryset = (
            Product.objects.filter(product_type=self.listing_type, owner=request.user)
            .select_related("owner")
            .order_by("-created_at")
        )
        queryset = self._apply_filters(queryset)
        page = self.paginate_queryset(queryset)
        serializer = ProductSerializer(
            page if page is not None else queryset,
            many=True,
            context={"request": request},
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response({"success": True, "results": serializer.data})

    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, pk=None):
        self._assert_can_modify(self.get_object())
        listing = self.get_object()
        listing.activate()
        return Response({"success": True, "product": ProductSerializer(listing).data})

    @action(detail=True, methods=["post"], url_path="deactivate")
    def deactivate(self, request, pk=None):
        self._assert_can_modify(self.get_object())
        listing = self.get_object()
        listing.deactivate()
        return Response({"success": True, "product": ProductSerializer(listing).data})

    @action(detail=True, methods=["post"], url_path="mark-sold")
    def mark_sold(self, request, pk=None):
        self._assert_can_modify(self.get_object())
        listing = self.get_object()
        listing.mark_sold()
        return Response({"success": True, "product": ProductSerializer(listing).data})

    @action(detail=True, methods=["post", "put"], url_path="images")
    def upload_image(self, request, pk=None):
        """POST an image or PUT the retained/reordered image references."""
        listing = self.get_object()
        self._assert_can_modify(listing)

        if request.method == "PUT":
            serializer = ProductImagesSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            images = serializer.validated_data["images"]
            if len(images) != len(set(images)) or any(
                image not in listing.images for image in images
            ):
                raise ValidationError(
                    {"images": "Only unique images already attached to this listing may be kept."}
                )
            listing.images = images
            listing.save(update_fields=["images", "updated_at"])
            return Response(
                {"success": True, "product": ProductSerializer(listing).data}
            )

        if len(listing.images) >= MAX_PRODUCT_IMAGES:
            raise ValidationError(
                {"image": "A listing may hold at most 8 images."}
            )

        serializer = ProductImageUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        image = serializer.validated_data["image"]
        ext = os.path.splitext(image.name)[1].lower() or ".jpg"
        filename = f"{listing.id}-{uuid.uuid4().hex}{ext}"
        relative = f"products/{listing.id}/{filename}"
        absolute = os.path.join(settings.MEDIA_ROOT, relative)
        os.makedirs(os.path.dirname(absolute), exist_ok=True)
        with open(absolute, "wb") as fh:
            for chunk in image.chunks():
                fh.write(chunk)

        listing.images = list(listing.images) + [f"{settings.MEDIA_URL}{relative}"]
        listing.save(update_fields=["images", "updated_at"])
        return Response(
            {"success": True, "product": ProductSerializer(listing).data},
            status=status.HTTP_201_CREATED,
        )


class FarmerListingViewSet(_BaseListingViewSet):
    """Farmer listings: POST as Farmer, GET as Wholesaler (FR-F-04/05, FR-W-02)."""

    queryset = Product.objects.none()  # only for schema lookup-type inference
    listing_type = ProductType.FARMER_LISTING
    creator_roles = (Role.FARMER,)
    reader_roles = FARMER_LISTING_READERS

    def get_permissions(self):
        if self.action == "create":
            return [IsFarmer()]
        if self.action in ("my", "mine"):
            return [IsFarmer()]
        return super().get_permissions()


class WholesalerListingViewSet(_BaseListingViewSet):
    """Wholesaler listings re-listed for Retailers (FR-W-05, FR-R-02/R-03)."""

    queryset = Product.objects.none()  # only for schema lookup-type inference
    listing_type = ProductType.WHOLESALER_LISTING
    creator_roles = (Role.WHOLESALER,)
    reader_roles = WHOLESALER_LISTING_READERS

    def get_permissions(self):
        if self.action in ("create", "my", "mine"):
            return [IsWholesaler()]
        if self.action == "list":
            # Retailers browse the marketplace; a wholesaler sees its own re-lists.
            return [IsAuthenticatedRole((Role.RETAILER, Role.WHOLESALER))]
        return super().get_permissions()


@extend_schema(responses=OpenApiTypes.OBJECT)
class CategoryListView(viewsets.ViewSet):
    """GET /api/v1/products/categories/ — filter dropdown metadata."""

    permission_classes = []

    def list(self, request):
        return Response(
            {
                "success": True,
                "categories": category_choices(),
                "units": unit_choices(),
            }
        )
