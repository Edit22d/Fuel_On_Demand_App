"""Domain models.

Money is stored as whole UGX integers everywhere — no floats in the ledger.
Every state change that matters financially goes through `core.services`.
"""
from decimal import Decimal

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from .utils import normalize_phone


# --------------------------------------------------------------------------- people
class Role(models.TextChoices):
    CUSTOMER = "customer", "Customer"
    RIDER = "rider", "Rider"
    TANKER = "tanker", "Tanker driver"
    STATION = "station", "Station staff"
    STAFF = "staff", "Staff"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, phone, password=None, **extra):
        if not phone:
            raise ValueError("A phone number is required")
        user = self.model(phone=normalize_phone(phone), **extra)
        user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra):
        extra.setdefault("role", Role.STAFF)
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("is_console_user", True)
        if extra.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True")
        return self.create_user(phone, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """One table for customers, riders and staff, separated by `role`."""

    phone = models.CharField(max_length=20, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    email = models.EmailField(blank=True)
    google_sub = models.CharField(max_length=128, unique=True, null=True, blank=True)
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.CUSTOMER, db_index=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)  # Django admin access
    is_console_user = models.BooleanField(default=False)  # FuelOnDemand console access
    is_suspended = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=True)
    console_title = models.CharField(max_length=60, blank=True, help_text="Job title shown in the console")

    emergency_contact = models.CharField(max_length=32, blank=True)
    wallet_balance = models.PositiveIntegerField(default=0)
    points = models.PositiveIntegerField(default=0)
    referral_code = models.CharField(max_length=12, blank=True)

    date_joined = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        ordering = ["-date_joined"]

    def __str__(self):
        return f"{self.name} ({self.phone})"

    @property
    def first_name(self):
        return self.name.split()[0] if self.name else self.phone

    @property
    def initials(self):
        parts = [p for p in self.name.split() if p][:2]
        return "".join(p[0] for p in parts).upper() or "FC"

    @property
    def can_use_console(self):
        return bool(self.is_active and self.is_console_user and not self.is_suspended)

    def get_full_name(self) -> str:
        return self.name

    def get_short_name(self) -> str:
        return self.first_name


class RiderProfile(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        SUSPENDED = "suspended", "Suspended"

    class VehicleType(models.TextChoices):
        BODA = "boda", "Boda (motorcycle)"
        CAR = "car", "Car"
        VAN = "van", "Van"
        TRUCK = "truck", "Truck"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="rider")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    vehicle_type = models.CharField(max_length=10, choices=VehicleType.choices, default=VehicleType.BODA)
    plate = models.CharField(max_length=16, blank=True)
    national_id = models.CharField(max_length=24, blank=True)
    permit_number = models.CharField(max_length=24, blank=True)

    online = models.BooleanField(default=False)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    rating = models.FloatField(default=5.0)
    deliveries_total = models.PositiveIntegerField(default=0)
    earnings_total = models.PositiveIntegerField(default=0)
    commission_pct = models.PositiveSmallIntegerField(default=12)

    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="rider_reviews"
    )
    reject_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.name} · {self.get_status_display()}"


# --------------------------------------------------------------------------- network
class Station(models.Model):
    class Brand(models.TextChoices):
        STABEX = "stabex", "Stabex"
        SHELL = "shell", "Shell"
        TOTAL = "total", "Total"
        HASHI = "hashi", "Hashi"
        OTHER = "other", "Independent"

    slug = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=90)
    brand = models.CharField(max_length=10, choices=Brand.choices, default=Brand.OTHER)
    address = models.CharField(max_length=160)
    lat = models.FloatField()
    lng = models.FloatField()
    rating = models.FloatField(default=4.8)
    reviews = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    opens_24h = models.BooleanField(default=True)
    service_radius_km = models.PositiveSmallIntegerField(default=12)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def price_map(self):
        return {p.fuel_type: p.price for p in self.prices.all()}

    def price_for(self, fuel_type: str) -> int | None:
        for p in self.prices.all():
            if p.fuel_type == fuel_type:
                return p.price
        return None


class FuelPrice(models.Model):
    class FuelType(models.TextChoices):
        PETROL = "petrol", "Petrol"
        DIESEL = "diesel", "Diesel"
        KEROSENE = "kerosene", "Kerosene"

    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="prices")
    fuel_type = models.CharField(max_length=10, choices=FuelType.choices, default=FuelType.PETROL)
    price = models.PositiveIntegerField(help_text="UGX per litre")
    previous_price = models.PositiveIntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("station", "fuel_type")]
        ordering = ["fuel_type"]

    def __str__(self):
        return f"{self.station.name} {self.fuel_type} @ {self.price}"

    @property
    def delta(self) -> int:
        if not self.previous_price:
            return 0
        return self.price - self.previous_price


# --------------------------------------------------------------------------- tankers
class StationStock(models.Model):
    """Litres on hand per forecourt, topped up by tanker offloads."""

    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="stock")
    fuel_type = models.CharField(max_length=10, choices=FuelPrice.FuelType.choices)
    litres = models.PositiveIntegerField(default=0)
    capacity_litres = models.PositiveIntegerField(default=30000)
    warning_pct = models.PositiveSmallIntegerField(default=20)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("station", "fuel_type")]
        ordering = ["station__name", "fuel_type"]

    def __str__(self):
        return f"{self.station.name} {self.fuel_type}: {self.litres:,} L"

    @property
    def level_pct(self) -> int:
        if not self.capacity_litres:
            return 0
        return min(100, round(self.litres * 100 / self.capacity_litres))

    @property
    def is_low(self) -> bool:
        return self.level_pct <= self.warning_pct


class Tanker(models.Model):
    """Bulk fuel truck. One row per plate; the driver is a User with role="tanker"."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        IDLE = "idle", "Idle"
        MAINTENANCE = "maintenance", "Maintenance"
        SUSPENDED = "suspended", "Suspended"

    plate = models.CharField(max_length=16, unique=True)
    make = models.CharField(max_length=40)
    model_name = models.CharField(max_length=40, blank=True)
    capacity_litres = models.PositiveIntegerField(default=20000)
    compartments = models.PositiveSmallIntegerField(default=4)
    fuel_class = models.CharField(
        max_length=10, choices=FuelPrice.FuelType.choices, default=FuelPrice.FuelType.DIESEL
    )
    driver = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="tankers",
        limit_choices_to={"role": Role.TANKER},
    )
    home_station = models.ForeignKey(
        Station, null=True, blank=True, on_delete=models.SET_NULL, related_name="tankers"
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.IDLE, db_index=True)
    is_verified = models.BooleanField(default=False)
    notes = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["plate"]

    def __str__(self):
        return f"{self.plate} ({self.make})"

    @property
    def title(self) -> str:
        return f"{self.make} {self.model_name}".strip()

    @property
    def open_trip(self):
        return self.trips.filter(status__in=TankerTrip.ACTIVE_STATUSES).select_related("station").first()


class TankerTrip(models.Model):
    """A bulk movement: depot -> station, with loaded/received reconciliation."""

    class Status(models.TextChoices):
        ASSIGNED = "assigned", "Assigned"
        ACCEPTED = "accepted", "Accepted"
        LOADED = "loaded", "Loaded"
        IN_TRANSIT = "in_transit", "In transit"
        ARRIVED = "arrived", "Arrived"
        OFFLOADED = "offloaded", "Offloaded"
        COMPLETED = "completed", "Reconciled"
        CANCELLED = "cancelled", "Cancelled"

    ACTIVE_STATUSES = [Status.ASSIGNED, Status.ACCEPTED, Status.LOADED, Status.IN_TRANSIT, Status.ARRIVED]

    reference = models.CharField(max_length=16, unique=True)
    tanker = models.ForeignKey(Tanker, on_delete=models.PROTECT, related_name="trips")
    driver = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="tanker_trips"
    )
    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="inbound_trips")
    origin = models.CharField(max_length=90, default="Kampala depot")
    fuel_type = models.CharField(max_length=10, choices=FuelPrice.FuelType.choices)
    assigned_litres = models.PositiveIntegerField()
    loaded_litres = models.PositiveIntegerField(null=True, blank=True)
    received_litres = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ASSIGNED, db_index=True)
    notes = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    assigned_at = models.DateTimeField(default=timezone.now)
    accepted_at = models.DateTimeField(null=True, blank=True)
    loaded_at = models.DateTimeField(null=True, blank=True)
    departed_at = models.DateTimeField(null=True, blank=True)
    arrived_at = models.DateTimeField(null=True, blank=True)
    offloaded_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "-created_at"])]

    def __str__(self):
        return f"{self.reference} {self.tanker.plate} -> {self.station.name}"

    @property
    def variance_litres(self) -> int:
        return (self.loaded_litres or 0) - (self.received_litres or 0)

    @property
    def variance_pct(self) -> float:
        if not self.loaded_litres:
            return 0.0
        return round(self.variance_litres * 100 / self.loaded_litres, 2)

    @property
    def in_progress(self) -> bool:
        return self.status in self.ACTIVE_STATUSES


class Vehicle(models.Model):
    class FuelClass(models.TextChoices):
        PETROL = "petrol", "Petrol"
        DIESEL = "diesel", "Diesel"

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="vehicles")
    plate = models.CharField(max_length=16)
    make = models.CharField(max_length=40)
    model = models.CharField(max_length=40, blank=True)
    fuel_class = models.CharField(max_length=10, choices=FuelClass.choices, default=FuelClass.PETROL)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.plate} · {self.make}"


class SavedPlace(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="places")
    label = models.CharField(max_length=40)
    address = models.CharField(max_length=160)
    lat = models.FloatField()
    lng = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["label"]

    def __str__(self):
        return f"{self.label} ({self.owner.phone})"


# --------------------------------------------------------------------------- orders
class Order(models.Model):
    class Status(models.TextChoices):
        PENDING_PAYMENT = "pending_payment", "Awaiting payment"
        CONFIRMED = "confirmed", "Confirmed"
        ASSIGNED = "assigned", "Rider assigned"
        PICKED_UP = "picked_up", "Picked up"
        ARRIVED = "arrived", "Arrived"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    ACTIVE_STATUSES = ("confirmed", "assigned", "picked_up", "arrived")

    class PaymentMethod(models.TextChoices):
        MOMO = "momo", "MTN MoMo"
        AIRTEL = "airtel", "Airtel Money"
        CARD = "card", "Card"
        WALLET = "wallet", "Wallet"
        CASH = "cash", "Cash on delivery"

    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", "Unpaid"
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        REFUNDED = "refunded", "Refunded"
        FAILED = "failed", "Failed"

    number = models.CharField(max_length=20, unique=True, db_index=True)
    customer = models.ForeignKey(User, on_delete=models.PROTECT, related_name="orders")
    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="orders")
    rider = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="deliveries"
    )

    fuel_type = models.CharField(max_length=10, choices=FuelPrice.FuelType.choices)
    litres = models.DecimalField(max_digits=6, decimal_places=1, validators=[MinValueValidator(Decimal("1"))])
    unit_price = models.PositiveIntegerField()
    fuel_total = models.PositiveIntegerField()
    delivery_fee = models.PositiveIntegerField(default=0)
    service_fee = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField()
    rider_pay = models.PositiveIntegerField(default=0)

    payment_method = models.CharField(max_length=10, choices=PaymentMethod.choices, default=PaymentMethod.MOMO)
    payment_status = models.CharField(
        max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID, db_index=True
    )
    payment_reference = models.CharField(max_length=60, blank=True)

    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING_PAYMENT, db_index=True
    )
    delivery_address = models.CharField(max_length=200)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)
    distance_km = models.FloatField(default=0)

    pickup_code = models.CharField(max_length=6, blank=True)
    delivery_code = models.CharField(max_length=4, blank=True)

    scheduled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    arrived_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=200, blank=True)

    rating = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    review = models.CharField(max_length=400, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["customer", "-created_at"]),
            models.Index(fields=["rider", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.number} · {self.get_status_display()}"

    @property
    def is_active(self) -> bool:
        return self.status in self.ACTIVE_STATUSES

    @property
    def eta_minutes(self) -> int:
        base = 12 + int(self.distance_km * 2.4)
        if self.status == self.Status.ASSIGNED:
            return base
        if self.status == self.Status.PICKED_UP:
            return max(4, base - 6)
        if self.status == self.Status.ARRIVED:
            return 1
        return base

    @property
    def status_rank(self) -> int:
        order = [s.value for s in self.Status]
        return order.index(self.status)

    @property
    def can_cancel(self) -> bool:
        return self.status in {
            self.Status.PENDING_PAYMENT,
            self.Status.CONFIRMED,
            self.Status.ASSIGNED,
        }


class OrderEvent(models.Model):
    """Append-only timeline for an order (who changed what, when)."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    status = models.CharField(max_length=16, choices=Order.Status.choices)
    note = models.CharField(max_length=200, blank=True)
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at"]


class OrderRejection(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="rejections")
    rider = models.ForeignKey(User, on_delete=models.CASCADE, related_name="rejections")
    reason = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class TrackingPing(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="pings")
    rider = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    lat = models.FloatField()
    lng = models.FloatField()
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["order", "-created_at"])]


# --------------------------------------------------------------------------- money
class Transaction(models.Model):
    class Kind(models.TextChoices):
        PAYMENT = "payment", "Order payment"
        TOPUP = "topup", "Wallet top-up"
        REFUND = "refund", "Refund"
        EARNING = "earning", "Rider earning"
        PAYOUT = "payout", "Rider payout"
        COMMISSION = "commission", "Platform commission"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESSFUL = "successful", "Successful"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="transactions")
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions")
    kind = models.CharField(max_length=12, choices=Kind.choices, db_index=True)
    method = models.CharField(max_length=10, choices=Order.PaymentMethod.choices, blank=True)
    amount = models.IntegerField(help_text="Signed UGX: credits positive, debits negative")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.SUCCESSFUL, db_index=True)
    reference = models.CharField(max_length=40, unique=True)
    note = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["kind", "-created_at"])]

    def __str__(self):
        return f"{self.reference} · {self.amount}"


# --------------------------------------------------------------------------- ops
class Notification(models.Model):
    class Kind(models.TextChoices):
        ORDER = "order", "Order"
        PROMO = "promo", "Promotion"
        SYSTEM = "system", "System"
        WALLET = "wallet", "Wallet"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=90)
    body = models.CharField(max_length=240)
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.SYSTEM)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_read(self) -> bool:
        return self.read_at is not None


class SupportTicket(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PENDING = "pending", "Waiting on customer"
        RESOLVED = "resolved", "Resolved"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"
        URGENT = "urgent", "Urgent"

    reference = models.CharField(max_length=14, unique=True)
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tickets")
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.SET_NULL, related_name="tickets")
    subject = models.CharField(max_length=120)
    message = models.TextField()
    reply = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True)
    priority = models.CharField(max_length=8, choices=Priority.choices, default=Priority.NORMAL)
    assignee = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_tickets"
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]


class AuditEvent(models.Model):
    """Security-relevant actions: logins, suspensions, refunds, price edits…"""

    class Severity(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        CRITICAL = "critical", "Critical"

    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_events")
    action = models.CharField(max_length=60, db_index=True)
    target = models.CharField(max_length=120, blank=True)
    meta = models.JSONField(default=dict, blank=True)
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.INFO, db_index=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} · {self.target}"


class OtpCode(models.Model):
    class Purpose(models.TextChoices):
        SIGNUP = "signup", "Sign up"
        LOGIN = "login", "Log in"
        RESET = "reset", "Password reset"

    phone = models.CharField(max_length=20, db_index=True)
    purpose = models.CharField(max_length=8, choices=Purpose.choices)
    code_hash = models.CharField(max_length=128)
    attempts = models.PositiveSmallIntegerField(default=0)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["phone", "purpose", "-created_at"])]


class Setting(models.Model):
    """Console-editable key/value store (fees, banner text, support phone…)."""

    key = models.CharField(max_length=60, unique=True)
    value = models.CharField(max_length=400, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return f"{self.key}={self.value}"
