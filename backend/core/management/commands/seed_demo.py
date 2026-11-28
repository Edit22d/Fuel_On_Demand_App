"""Populate the console with a believable two weeks of Kampala operations.

    python manage.py seed_demo            # add demo data if the database is empty
    python manage.py seed_demo --force    # wipe operations data and rebuild it

Deterministic (fixed RNG seed) so screenshots and charts stay comparable.
"""
from __future__ import annotations

import random
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import (
    AuditEvent,
    FuelPrice,
    Notification,
    Order,
    OrderEvent,
    OrderRejection,
    OtpCode,
    RiderProfile,
    SavedPlace,
    Station,
    StationStock,
    SupportTicket,
    Tanker,
    TankerTrip,
    TrackingPing,
    Transaction,
    User,
    Vehicle,
)
from core.utils import haversine_km, order_number, reference

RNG = random.Random(20261127)

STATIONS = [
    ("stabex", "Stabex Kira Road", "stabex", "Kira Road, Kampala · Open 24 hours", 0.3392, 32.5931, 4.9, 320, {"petrol": 6850, "diesel": 7150}),
    ("shell", "Shell Jinja Road", "shell", "Jinja Road, Kampala · Open 24 hours", 0.3316, 32.6104, 4.8, 275, {"petrol": 6950, "diesel": 7290}),
    ("total-ntinda", "Total Ntinda", "total", "Ntinda Road, Kampala · Open 24 hours", 0.3612, 32.6093, 4.7, 190, {"petrol": 6790, "diesel": 7080}),
    ("shell-kawempe", "Shell Kawempe", "shell", "Bombo Road, Kawempe · 6am – midnight", 0.3743, 32.5634, 4.6, 143, {"petrol": 6720, "diesel": 7040}),
    ("stabex-entebbe", "Stabex Entebbe Road", "stabex", "Entebbe Road, Kajjansi · Open 24 hours", 0.2076, 32.4849, 4.8, 211, {"petrol": 6890, "diesel": 7190}),
    ("hashi-bukoto", "Hashi Bukoto", "hashi", "Bukoto Street, Kamwokya · 5am – 11pm", 0.3524, 32.5912, 4.5, 96, {"petrol": 6750, "diesel": 6990}),
]

AREAS = [
    ("Kololo", 0.3476, 32.5975), ("Naguru", 0.3577, 32.6057), ("Bugolobi", 0.3217, 32.6188),
    ("Ntinda", 0.3612, 32.6122), ("Bukoto", 0.3503, 32.5937), ("Muyenga", 0.3024, 32.6018),
    ("Kira", 0.3809, 32.6623), ("Najjera", 0.3739, 32.6385), ("Wandegeya", 0.3386, 32.5788),
    ("Kabalagala", 0.3038, 32.5917), ("Kamwokya", 0.3439, 32.5881), ("Kawempe", 0.3740, 32.5589),
    ("Mengo", 0.3009, 32.5825), ("Luzira", 0.3096, 32.6348),
]

CUSTOMERS = [
    ("Brian Ssekitto", "+256700123456"), ("Aisha Nakato", "+256701234567"), ("Peter Okello", "+256702345678"),
    ("Grace Namutebi", "+256703456789"), ("Samuel Kiptoo", "+256704567890"), ("Faridah Nabirye", "+256705678901"),
    ("Josephine Atim", "+256706789012"), ("Daniel Mugisha", "+256707890123"), ("Sarah Kirabo", "+256708901234"),
    ("Emmanuel Ouma", "+256709012345"), ("Winnie Akello", "+256710123456"), ("Ronald Ssembatya", "+256711234567"),
    ("Miriam Nakiganda", "+256712345678"), ("Ivan Byaruhanga", "+256713456789"), ("Patience Asiimwe", "+256714567890"),
    ("Alex Tumwine", "+256715678901"), ("Brenda Kyalimpa", "+256716789012"), ("Moses Kirya", "+256717890123"),
    ("Judith Nalwoga", "+256718901234"), ("George Waiswa", "+256719012345"), ("Stella Achieng", "+256720123456"),
    ("Henry Ssuuna", "+256721234567"), ("Rita Nabbanja", "+256722345678"), ("Patrick Ekwaro", "+256723456789"),
    ("Esther Mirembe", "+256724567890"), ("Andrew Kizza", "+256725678901"), ("Lydia Namulindwa", "+256726789012"),
    ("Simon Ocaya", "+256727890123"), ("Joan Akurut", "+256728901234"), ("Denis Walusimbi", "+256729012345"),
    ("Mary Nansubuga", "+256730123456"), ("Charles Anguyo", "+256731234567"), ("Proscovia Nabaisa", "+256732345678"),
    ("Michael Ochieng", "+256733456789"), ("Harriet Nakku", "+256734567890"), ("Robert Mwesigwa", "+256735678901"),
]

RIDERS = [
    ("Isaac Kiyingi", "+256744000111", "boda", "UFX 411A", "approved"),
    ("Rashid Waiswa", "+256744000112", "boda", "UGK 908B", "approved"),
    ("Tony Lubega", "+256744000113", "boda", "UEM 332C", "approved"),
    ("Saul Mukasa", "+256744000114", "car", "UBG 771D", "approved"),
    ("Nelson Opio", "+256744000115", "boda", "UFJ 004E", "approved"),
    ("Abubakar Musisi", "+256744000116", "boda", "UER 662F", "approved"),
    ("Kevin Amanya", "+256744000117", "van", "UBH 219G", "approved"),
    ("Robert Ssekabira", "+256744000118", "boda", "UFD 887H", "approved"),
    ("Shafik Kamya", "+256744000119", "boda", "UEK 145J", "approved"),
    ("Joel Mubiru", "+256744000120", "car", "UBD 630K", "approved"),
    ("Peter Ainebyoona", "+256744000121", "boda", "UFM 512L", "pending"),
    ("Wilfred Oketch", "+256744000122", "van", "UBJ 088M", "pending"),
    ("Hakim Sserwadda", "+256744000123", "boda", "UEG 321N", "rejected"),
    ("Benard Nsubuga", "+256744000124", "boda", "UFK 765P", "approved"),
]

ROLLING = {"stabex": 6850, "shell": 6950, "total": 6790, "kawempe": 6720, "entebbe": 6890, "bukoto": 6750}
FUEL_MIX = ["petrol"] * 62 + ["diesel"] * 33 + ["kerosene"] * 5
METHODS = ["momo"] * 42 + ["airtel"] * 24 + ["card"] * 12 + ["wallet"] * 14 + ["cash"] * 8
CANCEL_REASONS = ["Station out of stock", "Ordered the wrong fuel type", "Changed my mind", "Rider taking too long"]


class Command(BaseCommand):
    help = "Create demo customers, riders, stations, two weeks of orders and the ledger."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Delete existing operations data first")

    @transaction.atomic
    def handle(self, *args, **options):
        if Order.objects.exists() and not options["force"]:
            self.stdout.write(self.style.WARNING("Orders already exist — pass --force to rebuild."))
            return
        if options["force"]:
            self._wipe()

        now = timezone.now()
        admin = self._console_users()
        stations = self._stations()
        customers = self._customers(now)
        riders = self._riders(now, admin)
        self._orders(now, stations, customers, riders, admin)
        self._tankers(now, stations)
        self._wallet_history(customers)
        self._tickets(customers, admin)
        self._audit(now, admin, riders)

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {Station.objects.count()} stations · {User.objects.count()} users · "
            f"{Order.objects.count()} orders · {Transaction.objects.count()} ledger entries · "
            f"{Tanker.objects.count()} tankers · {TankerTrip.objects.count()} bulk trips."
        ))
        self.stdout.write(f"Console login: {admin} / {self._admin_password()}")

    # ------------------------------------------------------------------ helpers
    def _admin_password(self) -> str:
        import os
        return os.getenv("FC_ADMIN_PASSWORD", "Console@2026")

    def _wipe(self) -> None:
        TankerTrip.objects.all().delete()
        Tanker.objects.all().delete()
        StationStock.objects.all().delete()
        TrackingPing.objects.all().delete()
        OrderEvent.objects.all().delete()
        OrderRejection.objects.all().delete()
        Transaction.objects.all().delete()
        Notification.objects.all().delete()
        SupportTicket.objects.all().delete()
        OtpCode.objects.all().delete()
        AuditEvent.objects.all().delete()
        Order.objects.all().delete()
        Vehicle.objects.all().delete()
        SavedPlace.objects.all().delete()
        RiderProfile.objects.all().delete()
        FuelPrice.objects.all().delete()
        Station.objects.all().delete()
        keep = list(
            User.objects.filter(is_console_user=True)
            .exclude(phone__in=["+256700000001", "+256700000002", "+256700000003"])
            .values_list("phone", flat=True)
        )
        User.objects.filter(is_superuser=False).exclude(phone__in=keep).delete()
        User.objects.filter(is_superuser=True).exclude(phone__in=["+256700000001"] + keep).delete()

    def _console_users(self) -> str:
        import os
        password = self._admin_password()
        people = [
            ("+256700000001", "Naomi Kirabo", "admin@fuelondemand.test", "Head of Operations", True),
            ("+256700000002", "Timothy Bwire", "dispatch@fuelondemand.test", "Dispatch Lead", False),
            ("+256700000003", "Sarah Nabukenya", "finance@fuelondemand.test", "Finance Manager", False),
        ]
        for phone, name, email, title, is_super in people:
            user, created = User.objects.get_or_create(
                phone=phone,
                defaults={
                    "name": name,
                    "email": email,
                    "role": "staff",
                    "is_staff": True,
                    "is_console_user": True,
                    "console_title": title,
                    "is_superuser": is_super,
                },
            )
            if created:
                user.set_password(password)
                user.save()
        return people[0][0]

    def _stations(self) -> list[Station]:
        made = []
        for slug, name, brand, address, lat, lng, rating, reviews, prices in STATIONS:
            station, _ = Station.objects.update_or_create(
                slug=slug,
                defaults=dict(name=name, brand=brand, address=address, lat=lat, lng=lng,
                              rating=rating, reviews=reviews, is_active=True),
            )
            for fuel_type, price in prices.items():
                FuelPrice.objects.update_or_create(
                    station=station, fuel_type=fuel_type, defaults={"price": price, "previous_price": price - 50}
                )
            made.append(station)
        return made

    def _customers(self, now) -> list[User]:
        people = []
        for index, (name, phone) in enumerate(CUSTOMERS):
            user, created = User.objects.get_or_create(
                phone=phone,
                defaults={
                    "name": name,
                    "role": "customer",
                    "points": RNG.randint(0, 900),
                    "wallet_balance": RNG.choice([0, 0, 5000, 12000, 25000, 48000]),
                    "date_joined": now - timedelta(days=RNG.randint(20, 240))
                    if index < len(CUSTOMERS) - 3 else now - timedelta(hours=RNG.randint(1, 18)),
                    "last_seen_at": now - timedelta(hours=RNG.randint(0, 72)),
                    "referral_code": f"FC{1000 + index}",
                },
            )
            if created:
                user.set_password("Fuel@2025")
                user.save()
            people.append(user)
        return people

    def _riders(self, now, admin_phone) -> list[User]:
        admin = User.objects.get(phone=admin_phone)
        approved = []
        for name, phone, vehicle, plate, status in RIDERS:
            user, created = User.objects.get_or_create(
                phone=phone,
                defaults={
                    "name": name,
                    "role": "rider",
                    "date_joined": now - timedelta(days=RNG.randint(14, 200)),
                    "wallet_balance": RNG.randint(0, 60000),
                },
            )
            if created:
                user.set_password("Rider@2025")
                user.save()
            profile, _ = RiderProfile.objects.update_or_create(
                user=user,
                defaults={
                    "status": status,
                    "vehicle_type": vehicle,
                    "plate": plate,
                    "national_id": f"CM{RNG.randint(100000, 999999)}",
                    "permit_number": f"PRM-{RNG.randint(10000, 99999)}",
                    "rating": round(RNG.uniform(4.3, 5.0), 2),
                    "online": status == "approved" and RNG.random() < 0.55,
                    "lat": 0.34 + RNG.uniform(-0.035, 0.035),
                    "lng": 32.58 + RNG.uniform(-0.04, 0.04),
                    "last_seen_at": now - timedelta(seconds=RNG.randint(10, 400)),
                    "reviewed_at": now - timedelta(days=RNG.randint(1, 20)) if status != "pending" else None,
                    "reviewed_by": admin if status != "pending" else None,
                    "reject_reason": "Permit photo unreadable, please re-upload." if status == "rejected" else "",
                },
            )
            if status == "approved":
                approved.append(user)
        return approved

    def _orders(self, now, stations, customers, riders, admin_phone) -> None:
        admin = User.objects.get(phone=admin_phone)
        today = timezone.localtime(now).date()
        seq_by_day: dict = {}
        online_riders = list(riders)

        for day_offset in range(13, -1, -1):
            day = today - timedelta(days=day_offset)
            weekend = day.weekday() >= 5
            count = RNG.randint(16, 26) + (6 if weekend else 0) + (4 if day_offset < 4 else 0)

            for _ in range(count):
                seq_by_day[day] = seq_by_day.get(day, 0) + 1
                station = RNG.choice(stations)
                customer = RNG.choice(customers)
                area, lat, lng = RNG.choice(AREAS)
                fuel = RNG.choice(FUEL_MIX)
                price = station.price_for(fuel) or 6800
                litres = Decimal(RNG.choice([5, 10, 10, 15, 20, 20, 25, 30, 40, 50]))
                fuel_total = int(litres * price)
                distance = haversine_km(station.lat, station.lng, lat, lng)
                delivery = 4000 + int(round(distance * 1200))
                total = fuel_total + delivery + 1500
                created = timezone.make_aware(
                    timezone.datetime(day.year, day.month, day.day, RNG.randint(7, 21), RNG.randint(0, 59))
                )
                method = RNG.choice(METHODS)

                if day_offset == 0 and RNG.random() < 0.55:
                    status = RNG.choice([Order.Status.CONFIRMED, Order.Status.ASSIGNED, Order.Status.PICKED_UP, Order.Status.ARRIVED])
                    created = now - timedelta(minutes=RNG.randint(3, 55))
                elif RNG.random() < 0.08:
                    status = Order.Status.CANCELLED
                elif RNG.random() < 0.02:
                    status = Order.Status.PENDING_PAYMENT
                else:
                    status = Order.Status.DELIVERED

                rider = RNG.choice(online_riders) if status not in {Order.Status.CONFIRMED, Order.Status.PENDING_PAYMENT, Order.Status.CANCELLED} else None
                rider_pay = int(round((3500 + distance * 900) / 500) * 500)

                order = Order(
                    number=order_number(seq_by_day[day], day),
                    customer=customer,
                    station=station,
                    rider=rider,
                    status=status,
                    fuel_type=fuel,
                    litres=litres,
                    unit_price=price,
                    fuel_total=fuel_total,
                    delivery_fee=delivery,
                    service_fee=1500,
                    total=total,
                    rider_pay=rider_pay,
                    payment_method=method,
                    delivery_address=f"{RNG.randint(2, 90)} {area}, Kampala",
                    lat=lat,
                    lng=lng,
                    note=RNG.choice(["", "", "", "Call when you reach the gate", "Blue gate, ask for Brian"]),
                    distance_km=distance,
                    created_at=created,
                    pickup_code=f"{RNG.randint(100000, 999999)}",
                    delivery_code=f"{RNG.randint(1000, 9999)}",
                )
                if status == Order.Status.CANCELLED:
                    order.payment_status = Order.PaymentStatus.REFUNDED
                    order.cancelled_at = created + timedelta(minutes=RNG.randint(4, 40))
                    order.cancel_reason = RNG.choice(CANCEL_REASONS)
                elif status == Order.Status.PENDING_PAYMENT:
                    order.payment_status = Order.PaymentStatus.PENDING
                else:
                    order.payment_status = Order.PaymentStatus.PAID
                if method == Order.PaymentMethod.CASH and status == Order.Status.DELIVERED:
                    order.payment_status = Order.PaymentStatus.PAID

                if status in {Order.Status.ASSIGNED, Order.Status.PICKED_UP, Order.Status.ARRIVED, Order.Status.DELIVERED}:
                    order.accepted_at = created + timedelta(minutes=RNG.randint(2, 9))
                if status in {Order.Status.PICKED_UP, Order.Status.ARRIVED, Order.Status.DELIVERED}:
                    order.picked_up_at = created + timedelta(minutes=RNG.randint(10, 25))
                if status in {Order.Status.ARRIVED, Order.Status.DELIVERED}:
                    order.arrived_at = created + timedelta(minutes=RNG.randint(26, 45))
                if status == Order.Status.DELIVERED:
                    order.delivered_at = created + timedelta(minutes=RNG.randint(46, 70))
                    order.rating = RNG.choice([5, 5, 5, 4, 4, 3])
                    order.review = RNG.choice(["Smooth delivery, thank you!", "", "Rider was very professional.", "", "Fuel arrived on time."])
                order.save()

                events = [(Order.Status.PENDING_PAYMENT, created)]
                if status != Order.Status.PENDING_PAYMENT:
                    events.append((Order.Status.CONFIRMED, created + timedelta(minutes=1)))
                if order.accepted_at:
                    events.append((Order.Status.ASSIGNED, order.accepted_at))
                if order.picked_up_at:
                    events.append((Order.Status.PICKED_UP, order.picked_up_at))
                if order.arrived_at:
                    events.append((Order.Status.ARRIVED, order.arrived_at))
                if order.delivered_at:
                    events.append((Order.Status.DELIVERED, order.delivered_at))
                if order.cancelled_at:
                    events.append((Order.Status.CANCELLED, order.cancelled_at))
                OrderEvent.objects.bulk_create([
                    OrderEvent(order=order, status=s, note="", created_at=at) for s, at in events
                ])

                if order.payment_status == Order.PaymentStatus.PAID:
                    Transaction.objects.create(
                        user=customer, order=order, kind=Transaction.Kind.PAYMENT,
                        method=method, amount=-total, reference=reference("TX", 10),
                        note=f"Payment for {order.number}", created_at=created + timedelta(minutes=1),
                    )
                if status == Order.Status.DELIVERED and rider:
                    Transaction.objects.create(
                        user=rider, order=order, kind=Transaction.Kind.EARNING, method="wallet",
                        amount=rider_pay, reference=reference("TX", 10),
                        note=f"Delivery pay for {order.number}", created_at=order.delivered_at,
                    )
                if order.payment_status == Order.PaymentStatus.REFUNDED:
                    Transaction.objects.create(
                        user=customer, order=order, kind=Transaction.Kind.REFUND, method=method,
                        amount=total, reference=reference("TX", 10),
                        note=f"Refund for {order.number}", created_at=order.cancelled_at,
                    )

                if status in {Order.Status.PICKED_UP, Order.Status.ARRIVED}:
                    self._pings(order, station, lat, lng, now)
                if rider and status in {Order.Status.PICKED_UP, Order.Status.ARRIVED}:
                    profile = rider.rider
                    profile.lat = order.lat + RNG.uniform(-0.004, 0.004)
                    profile.lng = order.lng + RNG.uniform(-0.004, 0.004)
                    profile.online = True
                    profile.last_seen_at = now
                    profile.save(update_fields=["lat", "lng", "online", "last_seen_at"])

        # A couple of pending applications and one live ticket per customer group.
        rejected = User.objects.filter(rider__status="rejected").first()
        pending = Order.objects.filter(status=Order.Status.CONFIRMED).first()
        if pending and rejected:
            OrderRejection.objects.create(order=pending, rider=rejected, reason="Too far from the station")

        # Rider aggregates from the delivered orders.
        for rider in riders:
            delivered = Order.objects.filter(rider=rider, status=Order.Status.DELIVERED)
            RiderProfile.objects.filter(user=rider).update(
                deliveries_total=delivered.count(),
                earnings_total=sum(o.rider_pay for o in delivered),
            )

        # Notifications for the last 10 orders.
        for order in Order.objects.select_related("customer", "station").order_by("-created_at")[:10]:
            Notification.objects.create(
                user=order.customer,
                title=f"Order {order.get_status_display().lower()}",
                body=f"{order.litres} L {order.fuel_type} · {order.station.name}",
                kind=Notification.Kind.ORDER,
                created_at=order.created_at + timedelta(minutes=2),
                read_at=order.created_at + timedelta(minutes=9) if RNG.random() < 0.5 else None,
            )

    def _pings(self, order: Order, station: Station, lat: float, lng: float, now) -> None:
        steps = 7
        for step in range(steps):
            ratio = step / (steps - 1)
            TrackingPing.objects.create(
                order=order,
                rider=order.rider,
                lat=station.lat + (lat - station.lat) * ratio + RNG.uniform(-0.0012, 0.0012),
                lng=station.lng + (lng - station.lng) * ratio + RNG.uniform(-0.0012, 0.0012),
                created_at=now - timedelta(seconds=(steps - step) * 40),
            )

    def _wallet_history(self, customers) -> None:
        for customer in RNG.sample(customers, 12):
            when = timezone.now() - timedelta(days=RNG.randint(1, 20))
            amount = RNG.choice([5000, 10000, 20000, 50000])
            Transaction.objects.create(
                user=customer, kind=Transaction.Kind.TOPUP, method=RNG.choice(["momo", "airtel", "card"]),
                amount=amount, reference=reference("TX", 10), note="Wallet top-up", created_at=when,
            )

    def _tickets(self, customers, admin_phone) -> None:
        admin = User.objects.get(phone=admin_phone)
        subjects = [
            ("Rider never arrived", "The rider marked the order as delivered but I never received the fuel.", "urgent", "open"),
            ("Wrong fuel type", "I ordered diesel but received petrol. Please advise.", "high", "open"),
            ("Refund not received", "My order was cancelled two days ago and the refund is missing.", "high", "pending"),
            ("Invoice request", "Please send a VAT invoice for order this week.", "normal", "resolved"),
            ("App login issue", "I cannot receive the OTP on my number.", "normal", "resolved"),
            ("Great service", "Just wanted to say the rider was excellent.", "low", "resolved"),
        ]
        for index, (subject, message, priority, status) in enumerate(subjects):
            customer = RNG.choice(customers)
            ticket = SupportTicket.objects.create(
                reference=f"SUP-{2400 + index}",
                customer=customer,
                order=Order.objects.filter(customer=customer).first(),
                subject=subject,
                message=message,
                priority=priority,
                status=status,
                assignee=admin if status != "open" else None,
                created_at=timezone.now() - timedelta(hours=RNG.randint(1, 60)),
            )
            if status == "resolved":
                ticket.reply = "Resolved by the dispatch team — thank you for the report."
                ticket.save(update_fields=["reply"])

    def _tankers(self, now, stations) -> None:
        """Tanker drivers, trucks, station stock and a week of bulk trips."""
        people = [
            ("+256755000101", "Moses Kabuye"),
            ("+256755000102", "Ali Ssekandi"),
            ("+256755000103", "Robert Kaggwa"),
            ("+256755000104", "Simon Ekwaro"),
            ("+256755000105", "David Kirabo"),
        ]
        drivers = []
        for phone, name in people:
            user, _ = User.objects.get_or_create(
                phone=phone, defaults={"name": name, "role": "tanker"}
            )
            drivers.append(user)

        fleet = [
            ("UBG 402T", "MAN", "TGX 26.440", 26000, 4, "diesel", drivers[0], Tanker.Status.ACTIVE),
            ("UBH 118S", "Scania", "R500", 32000, 6, "diesel", drivers[1], Tanker.Status.ACTIVE),
            ("UAG 734K", "Isuzu", "FVR 34", 18000, 4, "petrol", drivers[2], Tanker.Status.ACTIVE),
            ("UBJ 905L", "Hino", "500 Series", 20000, 4, "diesel", drivers[3], Tanker.Status.ACTIVE),
            ("UBK 221M", "Mercedes-Benz", "Actros 2645", 24000, 5, "diesel", drivers[4], Tanker.Status.ACTIVE),
            ("UBL 660P", "Sinotruk", "HOWO 371", 22000, 4, "petrol", drivers[4], Tanker.Status.MAINTENANCE),
        ]
        tanks = []
        for index, (plate, make, model, cap, comps, fuel_class, driver, status) in enumerate(fleet):
            tanker, _ = Tanker.objects.update_or_create(
                plate=plate,
                defaults={
                    "make": make,
                    "model_name": model,
                    "capacity_litres": cap,
                    "compartments": comps,
                    "fuel_class": fuel_class,
                    "driver": driver,
                    "home_station": stations[index % len(stations)],
                    "status": status,
                    "is_verified": index != 5,
                },
            )
            tanks.append(tanker)

        for station in stations:
            for fuel_type in station.price_map.keys():
                litres = RNG.randint(6000, 26000)
                if station.slug == "hashi-bukoto" and fuel_type == "petrol":
                    litres = 3400
                StationStock.objects.update_or_create(
                    station=station,
                    fuel_type=fuel_type,
                    defaults={"litres": litres, "capacity_litres": 30000},
                )

        stamp = timezone.localtime(now).strftime("%y%m%d")
        # tanker index, station index, fuel, assigned, loaded, received, status, hours ago
        plan = [
            (0, 0, "diesel", 24000, 23700, 23650, "completed", 104),
            (1, 1, "diesel", 30000, 29850, 29850, "completed", 92),
            (2, 2, "petrol", 17500, 17400, 17320, "completed", 76),
            (3, 3, "diesel", 19000, 18900, 18880, "completed", 61),
            (0, 4, "diesel", 25000, 24800, 24800, "completed", 45),
            (1, 5, "diesel", 28000, 28000, 27950, "completed", 30),
            (3, 2, "diesel", 18000, 18000, None, "cancelled", 27),
            (0, 3, "diesel", 22000, 21950, None, "in_transit", 4),
            (1, 4, "diesel", 26000, 25800, None, "in_transit", 2),
            (2, 5, "petrol", 17500, 17450, None, "arrived", 3),
            (3, 1, "diesel", 16000, None, None, "assigned", 1),
        ]
        for index, row in enumerate(plan, start=1):
            tanker_i, station_i, fuel, litres, loaded, received, status, hours = row
            tanker = tanks[tanker_i]
            base = now - timedelta(hours=hours)
            progress = {
                "assigned": 0, "accepted": 0, "cancelled": 0,
                "in_transit": 1, "arrived": 2, "offloaded": 3, "completed": 3,
            }[status]
            trip = TankerTrip.objects.create(
                reference=f"TRP-{stamp}-{index:03d}",
                tanker=tanker,
                driver=tanker.driver,
                station=stations[station_i % len(stations)],
                fuel_type=fuel,
                assigned_litres=litres,
                loaded_litres=loaded,
                received_litres=received,
                status=status,
                origin="Jinja depot",
                accepted_at=base + timedelta(minutes=12) if progress >= 1 else None,
                loaded_at=base + timedelta(minutes=38) if loaded else None,
                departed_at=base + timedelta(minutes=52) if progress >= 1 else None,
                arrived_at=base + timedelta(minutes=142) if progress >= 2 else None,
                offloaded_at=base + timedelta(minutes=171) if progress >= 3 else None,
                completed_at=base + timedelta(minutes=188) if status == "completed" else None,
                assigned_at=base,
            )
            TankerTrip.objects.filter(pk=trip.pk).update(created_at=base)

    def _audit(self, now, admin_phone, riders) -> None:
        admin = User.objects.get(phone=admin_phone)
        actions = [
            ("console.login", "Console", "info"),
            ("console.login_failed", "+256741000999", "warning"),
            ("rider.approved", "Isaac Kiyingi", "info"),
            ("price.updated", "Stabex Kira Road", "info"),
            ("order.refunded", "FOD-261126-0006", "warning"),
            ("console.lockout", "admin@fuelondemand.test", "critical"),
            ("customer.suspended", "Robert Mwesigwa", "warning"),
        ]
        for index, (action, target, severity) in enumerate(actions):
            AuditEvent.objects.create(
                actor=admin, action=action, target=target, severity=severity,
                meta={"demo": True}, ip="127.0.0.1", user_agent="FuelOnDemand console",
                created_at=now - timedelta(minutes=90 * index + 15),
            )
