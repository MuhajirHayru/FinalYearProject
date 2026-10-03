"""Marketplace, geospatial and image-upload tests (doc 5.1.5, FR-F-04..08, FR-R-02)."""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from products.models import Product, ProductStatus, ProductType
from users.models import AccountStatus, Role, User

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Visibility rules
# ---------------------------------------------------------------------------
def test_wholesaler_browser_sees_only_active_farmer_listings(api, wholesaler, farmer_product):
    farmer_product.status = ProductStatus.SOLD
    farmer_product.save()
    api.force_authenticate(user=wholesaler)
    response = api.get("/api/v1/products/farmer-listings/")
    assert response.status_code == 200
    assert response.data["results"] == []


def test_soft_deleted_listing_is_hidden(api, wholesaler, farmer_product):
    farmer_product.mark_deleted()
    api.force_authenticate(user=wholesaler)
    response = api.get("/api/v1/products/farmer-listings/")
    assert response.data["results"] == []


def test_retailer_browses_wholesaler_listings(api, retailer, wholesaler_product):
    api.force_authenticate(user=retailer)
    response = api.get("/api/v1/products/wholesaler-listings/")
    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["title"] == "Wholesale Tomato"


def test_farmer_cannot_browse_wholesaler_listings(api, farmer, wholesaler_product):
    api.force_authenticate(user=farmer)
    assert api.get("/api/v1/products/wholesaler-listings/").status_code == 403


def test_retailer_sees_distance_when_asking_for_proximity(api, retailer, wholesaler_product):
    api.force_authenticate(user=retailer)
    response = api.get("/api/v1/products/wholesaler-listings/", {"near_me": 1})
    assert response.status_code == 200
    row = response.data["results"][0]
    # Retailer and wholesaler are ~2 km apart in the fixtures.
    assert 0 <= row["distance_km"] < 10


def test_non_proximity_query_has_no_distance_field(api, wholesaler, farmer_product):
    """A wholesaler browsing without near_me gets no distance annotation."""
    api.force_authenticate(user=wholesaler)
    response = api.get("/api/v1/products/farmer-listings/")
    assert response.status_code == 200
    assert response.data["results"][0]["distance_km"] is None


def test_farmer_cannot_browse_the_farmer_marketplace(api, farmer, farmer_product):
    """Doc 5.1.5: farmers publish, wholesalers browse."""
    api.force_authenticate(user=farmer)
    assert api.get("/api/v1/products/farmer-listings/").status_code == 403


# -----------------------------------------------------------------------------
# Owner exemption on listing detail (regression: /farmer/listings/[id] 403'd)
# -----------------------------------------------------------------------------
def test_farmer_can_open_their_own_listing_detail(api, farmer, farmer_product):
    """A Farmer must reach the detail page of a listing they own (FR-F-05)."""
    api.force_authenticate(user=farmer)
    response = api.get(f"/api/v1/products/farmer-listings/{farmer_product.id}/")
    assert response.status_code == 200, response.data
    assert response.data["id"] == str(farmer_product.id)
    assert response.data["title"] == "Tomato"


def test_farmer_can_open_their_own_non_active_listing(api, farmer, farmer_product):
    """Own rows stay reachable whatever the status; buyers still see nothing."""
    for status in (
        ProductStatus.DRAFT,
        ProductStatus.INACTIVE,
        ProductStatus.SOLD,
        ProductStatus.DELETED,
    ):
        farmer_product.status = status
        farmer_product.save()
        api.force_authenticate(user=farmer)
        response = api.get(
            f"/api/v1/products/farmer-listings/{farmer_product.id}/"
        )
        assert response.status_code == 200, (status, response.data)
        assert response.data["status"] == status


def test_farmer_cannot_open_another_farmers_listing(api, farmer, farmer_b):
    """The owner exemption must not leak a competitor's listing."""
    other = Product.objects.create(
        title="Competitor Onion", quantity=40, price_per_unit=12,
        owner=farmer_b, product_type=ProductType.FARMER_LISTING,
    )
    api.force_authenticate(user=farmer)
    response = api.get(f"/api/v1/products/farmer-listings/{other.id}/")
    assert response.status_code in (403, 404)
    assert "Competitor Onion" not in str(response.data)


def test_farmer_cannot_browse_other_farmers_listings_via_the_list_endpoint(
    api, farmer, farmer_b
):
    """Adding the owner exemption must not open the marketplace to Farmers."""
    Product.objects.create(
        title="Competitor Onion", quantity=40, price_per_unit=12,
        owner=farmer_b, product_type=ProductType.FARMER_LISTING,
    )
    api.force_authenticate(user=farmer)
    assert api.get("/api/v1/products/farmer-listings/").status_code == 403


def test_reader_roles_are_unaffected_by_the_owner_exemption(
    api, wholesaler, retailer, user_admin, super_admin, farmer_product
):
    """Wholesaler/Admin/Super Admin keep browse rights on farmer listings."""
    url = f"/api/v1/products/farmer-listings/{farmer_product.id}/"
    for user in (wholesaler, user_admin, super_admin):
        api.force_authenticate(user=user)
        assert api.get(url).status_code == 200, user.role
    # A Retailer is in neither the reader nor the creator set for this table.
    api.force_authenticate(user=retailer)
    assert api.get(url).status_code in (403, 404)


def test_wholesaler_can_open_their_own_relisted_listing(api, wholesaler,
                                                         wholesaler_product):
    """The same exemption applies to the wholesaler re-listing table."""
    wholesaler_product.status = ProductStatus.SOLD
    wholesaler_product.save()
    api.force_authenticate(user=wholesaler)
    response = api.get(
        f"/api/v1/products/wholesaler-listings/{wholesaler_product.id}/"
    )
    assert response.status_code == 200, response.data
    assert response.data["status"] == ProductStatus.SOLD


def test_announcement_requires_the_message_key(api, super_admin):
    """The broadcast contract is AnnouncementSerializer { message } (FR-SA-04).

    Guards the bug where the UI posted ``{ announcement }`` and got a 400.
    """
    api.force_authenticate(user=super_admin)
    assert api.post(
        "/api/v1/superadmin/announcement/", {"message": "System go-live"}, format="json"
    ).status_code == 201
    # The old, wrong key must not be silently accepted.
    assert api.post(
        "/api/v1/superadmin/announcement/", {"announcement": "System go-live"},
        format="json",
    ).status_code == 400


# ---------------------------------------------------------------------------
# Proximity search (FR-R-02 / doc 6.2)
# ---------------------------------------------------------------------------
def test_proximity_filter_orders_by_distance(api, retailer, wholesaler):
    near = User.objects.create_user(
        email="near@test.et", password="demo1234", full_name="Near Wholesaler",
        role=Role.WHOLESALER, status=AccountStatus.APPROVED,
        latitude=9.0350, longitude=38.7400,
    )
    far = User.objects.create_user(
        email="far@test.et", password="demo1234", full_name="Far Wholesaler",
        role=Role.WHOLESALER, status=AccountStatus.APPROVED,
        latitude=9.5000, longitude=38.7400,
    )
    Product.objects.create(
        title="Far Produce", quantity=10, price_per_unit=5, owner=far,
        product_type=ProductType.WHOLESALER_LISTING,
    )
    Product.objects.create(
        title="Near Produce", quantity=10, price_per_unit=5, owner=near,
        product_type=ProductType.WHOLESALER_LISTING,
    )
    api.force_authenticate(user=retailer)
    # A radius implies near_me, and results are ranked closest-first.
    response = api.get("/api/v1/products/wholesaler-listings/", {"radius_km": 20})
    assert response.status_code == 200
    assert [row["title"] for row in response.data["results"]] == ["Near Produce"]


def test_proximity_ranks_all_results_by_distance(api, retailer, wholesaler):
    near = User.objects.create_user(
        email="near2@test.et", password="demo1234", full_name="Near Wholesaler",
        role=Role.WHOLESALER, status=AccountStatus.APPROVED,
        latitude=9.0350, longitude=38.7400,
    )
    for owner, title in ((wholesaler, "Mid Produce"), (near, "Nearest Produce")):
        Product.objects.create(
            title=title, quantity=10, price_per_unit=5, owner=owner,
            product_type=ProductType.WHOLESALER_LISTING,
        )
    api.force_authenticate(user=retailer)
    response = api.get("/api/v1/products/wholesaler-listings/", {"near_me": 1})
    distances = [row["distance_km"] for row in response.data["results"]]
    assert distances == sorted(distances)


def test_proximity_filter_rejects_non_numeric_radius(api, retailer):
    api.force_authenticate(user=retailer)
    response = api.get("/api/v1/products/wholesaler-listings/", {"radius_km": "abc"})
    assert response.status_code == 400
    assert "radius_km" in response.data["error"]


def test_proximity_requires_coordinates(api, wholesaler):
    blind = User.objects.create_user(
        email="blind@test.et", password="demo1234", full_name="No Coords",
        role=Role.WHOLESALER, status=AccountStatus.APPROVED,
    )
    api.force_authenticate(user=blind)
    response = api.get("/api/v1/products/wholesaler-listings/", {"near_me": 1})
    assert response.status_code == 400
    assert "near_me" in response.data["error"]


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
def test_category_and_price_filters(api, wholesaler, farmer_product):
    Product.objects.create(
        title="Onion", category="Root Crops", quantity=5, price_per_unit=10,
        owner=farmer_product.owner, product_type=ProductType.FARMER_LISTING,
    )
    api.force_authenticate(user=wholesaler)
    response = api.get(
        "/api/v1/products/farmer-listings/",
        {"category": "Root Crops", "min_price": 5, "max_price": 20},
    )
    assert [row["title"] for row in response.data["results"]] == ["Onion"]


def test_categories_endpoint_is_public():
    from rest_framework.test import APIClient

    response = APIClient().get("/api/v1/products/categories/")
    assert response.status_code == 200
    assert {"value", "label"} <= set(response.data["categories"][0])
    assert response.data["units"]


# ---------------------------------------------------------------------------
# Listing lifecycle
# ---------------------------------------------------------------------------
def test_listing_deactivate_then_reactivate(api, farmer, farmer_product):
    api.force_authenticate(user=farmer)
    response = api.post(f"/api/v1/products/farmer-listings/{farmer_product.id}/deactivate/")
    assert response.status_code == 200
    farmer_product.refresh_from_db()
    assert farmer_product.status == ProductStatus.INACTIVE

    response = api.post(f"/api/v1/products/farmer-listings/{farmer_product.id}/activate/")
    assert response.status_code == 200
    farmer_product.refresh_from_db()
    assert farmer_product.status == ProductStatus.ACTIVE


def test_mark_sold_out(api, farmer, farmer_product):
    api.force_authenticate(user=farmer)
    response = api.post(f"/api/v1/products/farmer-listings/{farmer_product.id}/mark-sold/")
    assert response.status_code == 200
    farmer_product.refresh_from_db()
    assert farmer_product.status == ProductStatus.SOLD


def test_delete_is_soft(api, farmer, farmer_product):
    api.force_authenticate(user=farmer)
    response = api.delete(f"/api/v1/products/farmer-listings/{farmer_product.id}/")
    assert response.status_code == 200
    farmer_product.refresh_from_db()
    assert farmer_product.status == ProductStatus.DELETED
    assert Product.objects.filter(pk=farmer_product.pk).exists()


def test_wholesaler_cannot_edit_farmer_listing(api, wholesaler, farmer_product):
    api.force_authenticate(user=wholesaler)
    response = api.patch(
        f"/api/v1/products/farmer-listings/{farmer_product.id}/",
        {"title": "Hijacked"},
        format="json",
    )
    assert response.status_code == 403


def test_update_changes_stock(api, farmer, farmer_product):
    api.force_authenticate(user=farmer)
    response = api.patch(
        f"/api/v1/products/farmer-listings/{farmer_product.id}/",
        {"quantity": "120"},
        format="json",
    )
    assert response.status_code == 200
    farmer_product.refresh_from_db()
    assert farmer_product.quantity == 120
    assert response.data["quantity"] == "120.00"


# ---------------------------------------------------------------------------
# Image upload (Pillow-backed ImageField)
# ---------------------------------------------------------------------------
def _png_bytes():
    # Smallest valid 1x1 PNG.
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def test_image_upload_appends_to_listing(api, farmer, farmer_product):
    api.force_authenticate(user=farmer)
    upload = SimpleUploadedFile("tomato.png", _png_bytes(), content_type="image/png")
    response = api.post(
        f"/api/v1/products/farmer-listings/{farmer_product.id}/images/",
        {"image": upload},
        format="multipart",
    )
    assert response.status_code == 201, response.data
    assert len(response.data["product"]["images"]) == 1
    farmer_product.refresh_from_db()
    assert len(farmer_product.images) == 1
    assert farmer_product.images[0].startswith("/media/products/")


def test_image_upload_rejects_non_image(api, farmer, farmer_product):
    api.force_authenticate(user=farmer)
    upload = SimpleUploadedFile(
        "evil.exe", b"MZ\x90\x00", content_type="application/octet-stream"
    )
    response = api.post(
        f"/api/v1/products/farmer-listings/{farmer_product.id}/images/",
        {"image": upload},
        format="multipart",
    )
    assert response.status_code == 400


def test_image_upload_forbidden_for_non_owner(api, wholesaler, farmer_product):
    api.force_authenticate(user=wholesaler)
    upload = SimpleUploadedFile("tomato.png", _png_bytes(), content_type="image/png")
    response = api.post(
        f"/api/v1/products/farmer-listings/{farmer_product.id}/images/",
        {"image": upload},
        format="multipart",
    )
    assert response.status_code == 403
