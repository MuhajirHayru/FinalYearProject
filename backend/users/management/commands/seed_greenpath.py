from django.core.management.base import BaseCommand
from django.utils import timezone

from chat.models import ChatChannel, Message
from notifications.models import Notification
from payments.models import Order, PaymentMethod, PaymentRecord, PaymentStatus
from products.models import Category, Product, ProductStatus, ProductType
from users.models import AccountStatus, PlatformSettings, Role, User

# Approximate regional coordinates so proximity search (FR-R-02) and the
# retailer dashboard ranking work against the seeded demo data.
COORDINATES = {
    "Addis Ababa": (9.0300, 38.7400),
    "Adama": (8.5400, 39.2700),
    "Bahir Dar": (11.5936, 37.3908),
    "Hawassa": (7.0621, 38.4764),
    "Jimma": (7.6667, 36.8333),
    "Mekelle": (13.4967, 39.4753),
    "Gondar": (12.6030, 37.4521),
    "Dire Dawa": (9.5931, 41.8661),
    "Nekemte": (9.0833, 36.5500),
    "Shashamane": (7.2000, 38.6000),
}


def _place(user, location):
    """Attach coordinates to a user whose location is known."""
    lat, lon = COORDINATES.get(location, (None, None))
    if lat is not None:
        user.latitude = lat
        user.longitude = lon
        user.save(update_fields=["latitude", "longitude"])
    return user


class Command(BaseCommand):
    help = "Seed Green Path demo data matching the frontend dashboards."

    def handle(self, *args, **options):
        if User.objects.filter(email="admin@greenpath.et").exists():
            self.stdout.write(self.style.WARNING("Seed data already present — skipping."))
            return

        # --- Users -------------------------------------------------------
        farmer = _place(
            User.objects.create_user(
                email="farmer@greenpath.et", password="demo1234",
                full_name="Gatienoricherd Alfas", phone="+251911000001",
                location="Bahir Dar", role=Role.FARMER, status=AccountStatus.APPROVED,
                privacy_policy_accepted=True,
            ),
            "Bahir Dar",
        )
        farmer2 = _place(
            User.objects.create_user(
                email="dawit@greenpath.et", password="demo1234",
                full_name="Dawit Bekele", phone="+251911000002",
                location="Adama", role=Role.FARMER, status=AccountStatus.APPROVED,
                privacy_policy_accepted=True,
            ),
            "Adama",
        )
        farmer3 = _place(
            User.objects.create_user(
                email="mekdes@greenpath.et", password="demo1234",
                full_name="Mekdes Alemu", phone="+251911000003",
                location="Hawassa", role=Role.FARMER, status=AccountStatus.APPROVED,
                privacy_policy_accepted=True,
            ),
            "Hawassa",
        )
        wholesaler = _place(
            User.objects.create_user(
                email="wholesaler@greenpath.et", password="demo1234",
                full_name="Abebe Mengesha", phone="+251911000004",
                location="Addis Ababa", role=Role.WHOLESALER, status=AccountStatus.APPROVED,
                privacy_policy_accepted=True,
            ),
            "Addis Ababa",
        )
        user_admin = _place(
            User.objects.create_user(
                email="admin@greenpath.et", password="demo1234",
                full_name="Hana Tesfaye", phone="+251911000005",
                location="Addis Ababa", role=Role.USER_ADMIN, status=AccountStatus.APPROVED,
                privacy_policy_accepted=True,
            ),
            "Addis Ababa",
        )
        fm = _place(
            User.objects.create_user(
                email="finance@greenpath.et", password="demo1234",
                full_name="Yohannes Finance", phone="+251911000006",
                location="Addis Ababa", role=Role.FINANCIAL_MANAGER, status=AccountStatus.APPROVED,
                privacy_policy_accepted=True,
            ),
            "Addis Ababa",
        )
        super_admin = _place(
            User.objects.create_user(
                email="superadmin@greenpath.et", password="demo1234",
                full_name="Green Path Super Admin", phone="+251911000007",
                location="Addis Ababa", role=Role.SUPER_ADMIN, status=AccountStatus.APPROVED,
                privacy_policy_accepted=True, is_staff=True, is_superuser=True,
            ),
            "Addis Ababa",
        )

        # Pending registrations for the admin approvals page
        pending = [
            ("Dawit Bekele", "dawit.bekele@mail.com", Role.FARMER, "Gondar"),
            ("Leta Tadesse", "leta.tadesse@mail.com", Role.WHOLESALER, "Addis Ababa"),
            ("Yonas Girma", "yonas.girma@mail.com", Role.RETAILER, "Adama"),
            ("Mekdes Alemu", "mekdes.alemu@mail.com", Role.FARMER, "Hawassa"),
            ("Samuel Haile", "samuel.haile@mail.com", Role.WHOLESALER, "Dire Dawa"),
            ("Berhanu Negash", "berhanu.n@gmail.com", Role.FARMER, "Mekelle"),
        ]
        for name, email, role, loc in pending:
            _place(
                User.objects.create_user(
                    email=email, password="demo1234", full_name=name,
                    location=loc, role=role, status=AccountStatus.PENDING,
                    privacy_policy_accepted=True,
                ),
                loc,
            )

        # Marketplace farmers (seller names shown on wholesaler page)
        def mk_farmer(name, loc, email):
            return _place(
                User.objects.create_user(
                    email=email, password="demo1234", full_name=name,
                    location=loc, role=Role.FARMER, status=AccountStatus.APPROVED,
                    privacy_policy_accepted=True,
                ),
                loc,
            )

        selam = mk_farmer("Selam Farm", "Adama", "selam@greenpath.et")
        valley = mk_farmer("Green Valley Farm", "Bahir Dar", "valley@greenpath.et")
        wollo = mk_farmer("Wollo Produce", "Gondar", "wollo@greenpath.et")
        tigray = mk_farmer("Tigray Organic Farm", "Mekelle", "tigray@greenpath.et")
        amhara = mk_farmer("Amhara Fruits", "Jimma", "amhara@greenpath.et")
        retailer = _place(
            User.objects.create_user(
                email="retailer@greenpath.et", password="demo1234",
                full_name="Mulu Retail Store", location="Addis Ababa",
                role=Role.RETAILER, status=AccountStatus.APPROVED, privacy_policy_accepted=True,
            ),
            "Addis Ababa",
        )

        # --- Farmer listings (dashboard table) --------------------------
        farmer_products = [
            ("Tomato", "Vegetables", 200, "kg", 25, farmer),
            ("Potato", "Root Crops", 350, "kg", 18, farmer),
            ("Onion", "Vegetables", 150, "kg", 22, farmer),
            ("Green Pepper", "Vegetables", 100, "kg", 30, farmer),
        ]
        farmer_listings = []
        for title, cat, qty, unit, price, owner in farmer_products:
            farmer_listings.append(Product.objects.create(
                title=title, category=cat, quantity=qty, unit_of_measure=unit,
                price_per_unit=price, owner=owner, product_type=ProductType.FARMER_LISTING,
                description=f"Fresh {title.lower()} straight from the farm.",
            ))

        # --- Marketplace listings (wholesaler page) ---------------------
        market = [
            ("Fresh Tomato", "Vegetables", selam, 25, 400),
            ("Potato", "Root Crops", valley, 18, 600),
            ("Red Onion", "Vegetables", wollo, 22, 350),
            ("Green Pepper", "Vegetables", tigray, 30, 220),
            ("Carrot", "Root Crops", amhara, 20, 300),
            ("Yellow Maize", "Grains", farmer2, 12, 2000),
            ("White Teff", "Grains", farmer3, 45, 800),
            ("Sesame Seed", "Spices", selam, 60, 500),
        ]
        market_products = []
        for title, cat, owner, price, qty in market:
            market_products.append(Product.objects.create(
                title=title, category=cat, quantity=qty, unit_of_measure="kg",
                price_per_unit=price, owner=owner, product_type=ProductType.FARMER_LISTING,
                description=f"Quality {title.lower()} available in bulk.",
            ))

        # A couple of sold listings for realism
        Product.objects.create(
            title="Mango", category=Category.FRUITS, quantity=0, unit_of_measure="kg",
            price_per_unit=35, owner=amhara, product_type=ProductType.FARMER_LISTING,
            status=ProductStatus.SOLD, description="Sweet organic mangoes.",
        )

        # --- Wholesaler re-listings (retailer dashboard, FR-R-02) --------
        relistings = [
            ("Bulk Tomato Crates", "Vegetables", 28, 500),
            ("Onion Sack (50kg)", "Vegetables", 24, 300),
            ("Teff 100kg Sack", "Grains", 52, 90),
            ("Mango Crate", "Fruits", 38, 120),
        ]
        for title, cat, price, qty in relistings:
            Product.objects.create(
                title=title, category=cat, quantity=qty, unit_of_measure="kg",
                price_per_unit=price, owner=wholesaler,
                product_type=ProductType.WHOLESALER_LISTING,
                description=f"{title} re-listed for retailers across the region.",
            )

        # --- Orders (wholesaler page table) -----------------------------
        orders_spec = [
            ("#ORD1234", selam, "Fresh Tomato", 180, "Shipped"),
            ("#ORD1233", valley, "Potato", 400, "Delivered"),
            ("#ORD1232", wollo, "Red Onion", 145, "Confirmed"),
            ("#ORD1231", tigray, "Green Pepper", 190, "Processing"),
            ("#ORD1230", amhara, "Carrot", 100, "Cancelled"),
        ]
        prod_by_title = {p.title: p for p in market_products}
        for ref, seller, title, qty, status in orders_spec:
            product = prod_by_title.get(title) or market_products[0]
            unit = float(product.price_per_unit)
            Order.objects.create(
                reference=ref, wholesaler=wholesaler, farmer=seller,
                product=product, quantity=qty, total_amount=qty * unit,
                status=status,
            )

        # --- Payments ----------------------------------------------------
        payments_spec = [
            (wholesaler, farmer2, "Yellow Maize", 14000, PaymentMethod.CBE_BIRR, "CBE-20250114", PaymentStatus.PENDING),
            (wholesaler, farmer3, "White Teff", 32500, PaymentMethod.TELEBIRR, "TLB-83204411", PaymentStatus.PENDING),
            (wholesaler, selam, "Sesame Seed", 58000, PaymentMethod.BANK_TRANSFER, "AWB-00193847", PaymentStatus.PENDING),
            (wholesaler, valley, "Potato", 21000, PaymentMethod.CBE_BIRR, "CBE-20250113", PaymentStatus.PENDING),
            (wholesaler, wollo, "Red Onion", 9600, PaymentMethod.TELEBIRR, "TLB-77103322", PaymentStatus.PENDING),
            (wholesaler, farmer, "Tomato", 1870, PaymentMethod.CBE_BIRR, "CBE-20250112", PaymentStatus.PENDING),
            (wholesaler, tigray, "Green Pepper", 15400, PaymentMethod.TELEBIRR, "TLB-55210099", PaymentStatus.PENDING),
            (wholesaler, amhara, "Carrot", 12000, PaymentMethod.BANK_TRANSFER, "AWB-00194001", PaymentStatus.PENDING),
        ]
        for w, f, title, amount, method, ref, status in payments_spec:
            product = prod_by_title.get(title) or farmer_listings[0]
            PaymentRecord.objects.create(
                submitted_by=w, farmer=f, product=product, amount=amount,
                payment_method=method, reference_number=ref, status=status,
            )
        # Bulk historical verified payments (tab counts: 43 verified, 3 flagged)
        import datetime as dt
        base = dt.date(2025, 1, 10)
        for i in range(43):
            product = market_products[i % len(market_products)]
            p = PaymentRecord.objects.create(
                submitted_by=wholesaler, farmer=product.owner, product=product,
                amount=5000 + i * 250,
                payment_method=[m for m in PaymentMethod.values][i % 3],
                reference_number=f"HIST-{1000 + i}",
                status=PaymentStatus.VERIFIED,
                verified_by=fm,
            )
            PaymentRecord.objects.filter(pk=p.pk).update(
                verified_at=timezone.make_aware(dt.datetime.combine(base + dt.timedelta(days=i % 20), dt.time(10, 0)))
            )
        for i in range(3):
            product = market_products[i % len(market_products)]
            PaymentRecord.objects.create(
                submitted_by=wholesaler, farmer=product.owner, product=product,
                amount=7000 + i * 1000,
                payment_method=PaymentMethod.TELEBIRR,
                reference_number=f"FLAG-{200 + i}",
                status=PaymentStatus.FLAGGED,
                notes="Reference number mismatch — please confirm with the bank.",
                verified_by=fm,
            )
        # One irreconcilable case so the DISPUTED tab is populated.
        disputed_product = market_products[4]
        PaymentRecord.objects.create(
            submitted_by=wholesaler, farmer=disputed_product.owner,
            product=disputed_product, amount=12500,
            payment_method=PaymentMethod.CBE_BIRR, reference_number="CBE-20250102",
            status=PaymentStatus.DISPUTED,
            notes="Farmer disputes receipt — escalated for manual settlement.",
            verified_by=fm,
        )

        # --- Chat channels + messages (farmer unread badge = 2) -----------
        channel = ChatChannel.objects.create(related_product=farmer_listings[0])
        channel.participants.add(farmer, wholesaler)
        Message.objects.create(channel=channel, sender=wholesaler,
                               content='Hi, is the "Tomato" listing still available for 200 kg?')
        Message.objects.create(channel=channel, sender=farmer,
                               content="Yes, fresh stock. I can do 25 ETB per kg.")
        Message.objects.create(channel=channel, sender=wholesaler,
                               content="Great — I will submit a payment record today.")
        retail_channel = ChatChannel.objects.create(related_product=farmer_listings[1])
        retail_channel.participants.add(retailer, wholesaler)
        Message.objects.create(
            channel=retail_channel, sender=wholesaler,
            content='Are the "Potato" re-lists delivered to Addis every Tuesday?',
        )
        from django.utils import timezone as tz
        for ch in (channel, retail_channel):
            ch.last_message_at = tz.now()
            ch.save(update_fields=["last_message_at"])

        # --- Notifications ------------------------------------------------
        Notification.objects.create(
            recipient=farmer, type="MESSAGE",
            message='New message from Abebe Mengesha about "Tomato"',
        )
        Notification.objects.create(
            recipient=farmer, type="PRODUCT",
            message='Your listing "Potato" was viewed by 5 wholesalers',
        )
        Notification.objects.create(
            recipient=farmer, type="ORDER",
            message='Your listing "Onion" received a new order',
        )
        Notification.objects.create(
            recipient=wholesaler, type="ORDER",
            message="Order #ORD1234 has been shipped by Selam Farm",
        )
        Notification.objects.create(
            recipient=wholesaler, type="PAYMENT",
            message="Order #ORD1233 has been delivered",
        )
        Notification.objects.create(
            recipient=retailer, type="SYSTEM",
            message="Welcome to Green Path — 4 new wholesale listings near you.",
        )

        # --- Platform banner ---------------------------------------------
        config = PlatformSettings.load()
        config.announcement = (
            "Demo environment: verification is simulated, no real money moves."
        )
        config.save(update_fields=["announcement", "updated_at"])

        self.stdout.write(self.style.SUCCESS("Green Path demo data seeded."))
        self.stdout.write("Logins (password: demo1234):")
        self.stdout.write("  farmer@greenpath.et      — Farmer dashboard")
        self.stdout.write("  wholesaler@greenpath.et  — Wholesaler marketplace")
        self.stdout.write("  retailer@greenpath.et    — Retailer discovery")
        self.stdout.write("  admin@greenpath.et       — Pending approvals")
        self.stdout.write("  finance@greenpath.et     — Payment management")
        self.stdout.write("  superadmin@greenpath.et  — Super admin")
