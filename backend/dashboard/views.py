"""Role dashboard aggregation endpoints (doc 5.1.5, FR-F-06, FR-W-07, FR-R-05, FR-SA-05)."""
from django.db.models import Count, Q, Sum
from django.utils import timezone

from chat.models import Message
from notifications.models import Notification
from payments.models import Order, OrderStatus, PaymentRecord, PaymentStatus
from products.geo import annotate_distance_km
from products.models import Product, ProductStatus, ProductType
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema

from users.models import AccountStatus, Role, User
from users.permissions import (
    IsFarmer,
    IsFinancialManager,
    IsRetailer,
    IsUserAdmin,
    IsWholesaler,
)


def _unread_message_count(user):
    return Message.objects.filter(
        channel__participants=user, is_read=False
    ).exclude(sender=user).count()


def _recent_activity(user, fallback=None, limit=6):
    """Newest notifications, falling back to domain events when empty."""
    items = [
        {
            "type": n.type,
            "text": n.message,
            "time": _relative(n.created_at),
        }
        for n in Notification.objects.filter(recipient=user)[:limit]
    ]
    if not items and fallback:
        items = fallback()
    return items


def _relative(dt):
    if not dt:
        return ""
    seconds = int((timezone.now() - dt).total_seconds())
    if seconds < 60:
        return "Just now"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 86400:
        hours = seconds // 3600
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    days = seconds // 86400
    if days == 1:
        return "Yesterday"
    if days < 7:
        return f"{days} days ago"
    return dt.strftime("%d %b %Y")


@extend_schema(responses=OpenApiTypes.OBJECT)
class FarmerDashboardView(APIView):
    """GET /api/v1/dashboard/farmer/ (FR-F-06)."""

    permission_classes = [IsFarmer]

    def get(self, request):
        user = request.user
        listings = Product.objects.filter(
            owner=user, product_type=ProductType.FARMER_LISTING
        )
        orders_received = Order.objects.filter(farmer=user)
        payments = PaymentRecord.objects.filter(farmer=user)
        verified = payments.filter(status=PaymentStatus.VERIFIED)

        def fallback():
            return [
                {
                    "type": "ORDER",
                    "text": f"Order {o.reference} from {o.wholesaler.full_name}",
                    "time": _relative(o.created_at),
                }
                for o in orders_received.select_related("wholesaler")[:5]
            ]

        return Response(
            {
                "success": True,
                "stats": {
                    "total_active_listings": listings.filter(
                        status=ProductStatus.ACTIVE
                    ).count(),
                    "total_products_sold": int(
                        orders_received.open().aggregate(t=Sum("quantity"))["t"] or 0
                    ),
                    "unread_messages": _unread_message_count(user),
                    "total_listings": listings.count(),
                    "pending_orders": orders_received.filter(
                        status=OrderStatus.PROCESSING
                    ).count(),
                    "total_earned": int(verified.aggregate(t=Sum("amount"))["t"] or 0),
                    "pending_payments": payments.filter(
                        status=PaymentStatus.PENDING
                    ).count(),
                },
                "listings": [
                    {
                        "id": str(p.id),
                        "title": p.title,
                        "quantity": str(p.quantity),
                        "unit": p.unit_of_measure,
                        "price_per_unit": str(p.price_per_unit),
                        "status": p.status,
                    }
                    for p in listings.filter(status=ProductStatus.ACTIVE)[:20]
                ],
                "recent_activity": _recent_activity(user, fallback),
            }
        )


@extend_schema(responses=OpenApiTypes.OBJECT)
class WholesalerDashboardView(APIView):
    """GET /api/v1/dashboard/wholesaler/ (FR-W-07)."""

    permission_classes = [IsWholesaler]

    def get(self, request):
        user = request.user
        orders = Order.objects.filter(wholesaler=user).select_related(
            "farmer", "product"
        )
        payments = PaymentRecord.objects.filter(submitted_by=user)

        def fallback():
            return [
                {
                    "type": "ORDER",
                    "text": f"Order {o.reference} - {o.get_status_display()}",
                    "time": _relative(o.created_at),
                }
                for o in orders[:5]
            ]

        return Response(
            {
                "success": True,
                "stats": {
                    "total_orders": orders.count(),
                    "total_spent": int(
                        orders.open().aggregate(t=Sum("total_amount"))["t"] or 0
                    ),
                    "favorite_sellers": Order.objects.filter(wholesaler=user)
                    .values("farmer")
                    .distinct()
                    .count(),
                    "unread_messages": _unread_message_count(user),
                    "active_listings": Product.objects.filter(
                        owner=user, status=ProductStatus.ACTIVE
                    ).count(),
                    "pending_orders": orders.filter(
                        status=OrderStatus.PROCESSING
                    ).count(),
                    "pending_payments": payments.filter(
                        status=PaymentStatus.PENDING
                    ).count(),
                    "verified_payments": payments.filter(
                        status=PaymentStatus.VERIFIED
                    ).count(),
                },
                "orders": [
                    {
                        "id": str(o.id),
                        "reference": o.reference,
                        "seller": o.farmer.full_name,
                        "product": o.product.title,
                        "total": f"{o.total_amount:,.0f} ETB",
                        "status": o.status,
                        "date": o.created_at.strftime("%b %d, %Y"),
                    }
                    for o in orders[:10]
                ],
                "recent_activity": _recent_activity(user, fallback),
            }
        )


@extend_schema(responses=OpenApiTypes.OBJECT)
class RetailerDashboardView(APIView):
    """GET /api/v1/dashboard/retailer/ (FR-R-05).

    Surfaces browsing activity and active communications, plus the nearest
    wholesaler listings the retailer can discover (FR-R-02).
    """
    permission_classes = [IsRetailer]

    def get(self, request):
        user = request.user
        channels = Message.objects.filter(channel__participants=user)
        listings = Product.objects.filter(
            product_type=ProductType.WHOLESALER_LISTING,
            status=ProductStatus.ACTIVE,
        ).select_related("owner")

        ranked, has_origin = annotate_distance_km(listings, user)
        if has_origin:
            ranked = ranked.order_by("distance_km", "-created_at")[:8]
        else:
            ranked = ranked.order_by("-created_at")[:8]

        nearby = [
            {
                "id": str(p.id),
                "title": p.title,
                "wholesaler": p.owner.full_name,
                "location": p.owner.location,
                "price_per_unit": str(p.price_per_unit),
                "unit": p.unit_of_measure,
                "distance_km": round(float(p.distance_km), 2)
                if getattr(p, "distance_km", None) is not None
                else None,
            }
            for p in ranked
        ]

        active_channels = (
            channels.values("channel")
            .distinct()
            .count()
        )

        return Response(
            {
                "success": True,
                "stats": {
                    "active_communications": active_channels,
                    "unread_messages": _unread_message_count(user),
                    "total_wholesalers": User.objects.filter(
                        role=Role.WHOLESALER, status=AccountStatus.APPROVED
                    ).count(),
                    "available_listings": listings.count(),
                    "nearby_listings": len(nearby),
                    "location_available": has_origin,
                },
                "nearby_listings": nearby,
                "recent_activity": _recent_activity(user),
            }
        )


@extend_schema(responses=OpenApiTypes.OBJECT)
class AdminDashboardView(APIView):
    """GET /api/v1/dashboard/admin/ — User Admin / Financial Manager overview."""

    permission_classes = [IsUserAdmin | IsFinancialManager]

    def get(self, request):
        pending_users = User.objects.filter(status=AccountStatus.PENDING)
        by_role = dict(
            User.objects.filter(status=AccountStatus.APPROVED)
            .values_list("role")
            .annotate(c=Count("id"))
            .values_list("role", "c")
        )
        return Response(
            {
                "success": True,
                "stats": {
                    "pending_users": pending_users.count(),
                    "total_users": User.objects.count(),
                    "active_users": User.objects.filter(
                        status=AccountStatus.APPROVED
                    ).count(),
                    "farmers": by_role.get(Role.FARMER, 0),
                    "wholesalers": by_role.get(Role.WHOLESALER, 0),
                    "retailers": by_role.get(Role.RETAILER, 0),
                    "active_listings": Product.objects.filter(
                        status=ProductStatus.ACTIVE
                    ).count(),
                    "pending_payments": PaymentRecord.objects.filter(
                        status=PaymentStatus.PENDING
                    ).count(),
                    "verified_payments": PaymentRecord.objects.filter(
                        status=PaymentStatus.VERIFIED
                    ).count(),
                    "flagged_payments": PaymentRecord.objects.filter(
                        status=PaymentStatus.FLAGGED
                    ).count(),
                    "total_orders": Order.objects.count(),
                },
            }
        )


@extend_schema(responses=OpenApiTypes.OBJECT)
class PaymentSummaryView(APIView):
    """GET /api/v1/dashboard/payments/ — Payment Management tab summary (FR-FM-01)."""

    permission_classes = [IsFinancialManager]

    def get(self, request):
        now = timezone.now()
        pending = PaymentRecord.objects.pending()
        verified = PaymentRecord.objects.verified().filter(
            verified_at__year=now.year, verified_at__month=now.month
        )
        flagged = PaymentRecord.objects.flagged()

        return Response(
            {
                "success": True,
                "summary": {
                    "pending_amount": int(pending.aggregate(t=Sum("amount"))["t"] or 0),
                    "pending_count": pending.count(),
                    "verified_amount": int(verified.aggregate(t=Sum("amount"))["t"] or 0),
                    "verified_count": verified.count(),
                    "flagged_count": flagged.count(),
                    "flagged_amount": int(flagged.aggregate(t=Sum("amount"))["t"] or 0),
                },
                "tabs": {
                    "PENDING": pending.count(),
                    "VERIFIED": PaymentRecord.objects.verified().count(),
                    "FLAGGED": flagged.count(),
                    "DISPUTED": PaymentRecord.objects.filter(
                        status=PaymentStatus.DISPUTED
                    ).count(),
                },
            }
        )
