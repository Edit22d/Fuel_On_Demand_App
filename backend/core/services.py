"""Business rules: pricing, the order state machine, wallet/ledger, OTP, audit.

Every write that moves money or changes an order status goes through here so the
mobile API and the console can never drift apart.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
import logging

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import (
    AuditEvent,
    Notification,
    Order,
    OrderEvent,
    OtpCode,
    RiderProfile,
    Role,
    Station,
    StationStock,
    Tanker,
    TankerTrip,
    Transaction,
    User,
)
from .utils import client_ip, haversine_km, numeric_code, order_number, reference

FC = settings.FC
logger = logging.getLogger("fuelondemand.security")


class DomainError(Exception):
    """Recoverable business-rule failure → HTTP 409/422 with `message`."""


# --------------------------------------------------------------------------- pricing
def get_setting(key: str, default: str = "") -> str:
    from .models import Setting

    row = Setting.objects.filter(key=key).first()
    return row.value if row else default


def get_setting_int(key: str, default: int) -> int:
    try:
        return int(get_setting(key, str(default)))
    except (TypeError, ValueError):
        return default


def set_setting(key: str, value: str, actor=None) -> None:
    from .models import Setting

    Setting.objects.update_or_create(
        key=key, defaults={"value": str(value)[:400], "updated_by": actor if actor and actor.is_authenticated else None}
    )


def quote(station: Station, fuel_type: str, litres, lat: float | None = None, lng: float | None = None) -> dict:
    unit_price = station.price_for(fuel_type)
    if not unit_price:
        raise DomainError(f"{station.name} does not sell {fuel_type} right now.")

    litres = Decimal(str(litres)).quantize(Decimal("0.1"))
    if litres < 1 or litres > 500:
        raise DomainError("Litres must be between 1 and 500.")

    fuel_total = int((litres * unit_price).to_integral_value())
    distance = haversine_km(station.lat, station.lng, lat or 0.3476, lng or 32.5825)
    delivery_fee = get_setting_int("delivery_base", FC["delivery_base"]) + int(
        round(distance * get_setting_int("delivery_per_km", FC["delivery_per_km"]))
    )
    service_fee = get_setting_int("service_fee", FC["service_fee"])
    rider_pay = FC["rider_base_pay"] + int(round(distance * FC["rider_pay_per_km"]))
    rider_pay = int(round(rider_pay / FC["rider_pay_round"]) * FC["rider_pay_round"])

    return {
        "fuel_type": fuel_type,
        "litres": litres,
        "unit_price": unit_price,
        "fuel_total": fuel_total,
        "delivery_fee": delivery_fee,
        "service_fee": service_fee,
        "total": fuel_total + delivery_fee + service_fee,
        "rider_pay": rider_pay,
        "distance_km": distance,
        "eta_minutes": 14 + int(round(distance * 2.4)),
    }


# --------------------------------------------------------------------------- ledger
def record_transaction(*, user, kind, amount, method="", status="successful", order=None, note="", when=None) -> Transaction:
    return Transaction.objects.create(
        user=user,
        order=order,
        kind=kind,
        amount=amount,
        method=method,
        status=status,
        reference=reference("TX"),
        note=note,
        created_at=when or timezone.now(),
    )


def credit_wallet(user: User, amount: int, *, kind=Transaction.Kind.TOPUP, note="", order=None) -> Transaction:
    if amount <= 0:
        raise DomainError("Amount must be positive.")
    with transaction.atomic():
        User.objects.filter(pk=user.pk).update(wallet_balance=F("wallet_balance") + amount)
        user.refresh_from_db(fields=["wallet_balance"])
        return record_transaction(user=user, kind=kind, amount=amount, method="wallet", order=order, note=note)


def debit_wallet(user: User, amount: int, *, note="", order=None) -> Transaction:
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=user.pk)
        if locked.wallet_balance < amount:
            raise DomainError("Your wallet balance is too low for this order.")
        User.objects.filter(pk=user.pk).update(wallet_balance=F("wallet_balance") - amount)
        user.refresh_from_db(fields=["wallet_balance"])
        return record_transaction(
            user=user, kind=Transaction.Kind.PAYMENT, amount=-amount, method="wallet", order=order, note=note
        )


# --------------------------------------------------------------------------- orders
def create_order(
    *,
    customer: User,
    station: Station,
    fuel_type: str,
    litres,
    payment_method: str,
    delivery_address: str,
    lat: float | None = None,
    lng: float | None = None,
    note: str = "",
    scheduled_at=None,
    created_at=None,
) -> Order:
    if customer.is_suspended:
        raise DomainError("This account is suspended. Contact support.")

    priced = quote(station, fuel_type, litres, lat, lng)
    priced.pop("eta_minutes", None)  # derived property on Order, not a stored column
    created_at = created_at or timezone.now()
    with transaction.atomic():
        seq = Order.objects.filter(created_at__date=timezone.localtime(created_at).date()).count() + 1
        order = Order.objects.create(
            number=order_number(seq),
            customer=customer,
            station=station,
            payment_method=payment_method,
            delivery_address=delivery_address,
            lat=lat,
            lng=lng,
            note=note,
            scheduled_at=scheduled_at,
            pickup_code=numeric_code(6),
            delivery_code=numeric_code(4),
            created_at=created_at,
            **priced,
        )
        log_event(order, Order.Status.PENDING_PAYMENT, actor=customer, note="Order placed")

    pay_order(order)
    return order


def pay_order(order: Order) -> Order:
    """Sandbox payments settle instantly; cash stays unpaid until delivery."""
    method = order.payment_method
    if method == Order.PaymentMethod.CASH:
        order.payment_status = Order.PaymentStatus.UNPAID
        order.save(update_fields=["payment_status"])
        return confirm_order(order)

    if method == Order.PaymentMethod.WALLET:
        debit_wallet(order.customer, order.total, order=order, note=f"Payment for {order.number}")
    elif FC["payment_driver"] == "sandbox":
        record_transaction(
            user=order.customer,
            kind=Transaction.Kind.PAYMENT,
            amount=-order.total,
            method=method,
            order=order,
            note=f"{order.number} settled by sandbox gateway",
        )
        order.payment_reference = reference("PAY", 10)
    else:
        record_transaction(
            user=order.customer,
            kind=Transaction.Kind.PAYMENT,
            amount=-order.total,
            method=method,
            status=Transaction.Status.PENDING,
            order=order,
            note=f"{order.number} awaiting gateway confirmation",
        )
        order.payment_status = Order.PaymentStatus.PENDING
        order.save(update_fields=["payment_status", "payment_reference"])
        return order

    order.payment_status = Order.PaymentStatus.PAID
    order.save(update_fields=["payment_status", "payment_reference"])
    return confirm_order(order)


def confirm_order(order: Order) -> Order:
    if order.status != Order.Status.PENDING_PAYMENT:
        return order
    order.status = Order.Status.CONFIRMED
    order.save(update_fields=["status"])
    log_event(order, Order.Status.CONFIRMED, note="Payment confirmed")
    notify(
        order.customer,
        "Order confirmed",
        f"{order.litres} L of {order.fuel_type} from {order.station.name} is being prepared.",
        Notification.Kind.ORDER,
    )
    return order


def assign_rider(order: Order, rider: User, actor: User | None = None) -> Order:
    if order.status not in {Order.Status.CONFIRMED, Order.Status.ASSIGNED}:
        raise DomainError(f"{order.number} cannot be assigned while {order.get_status_display().lower()}.")
    profile = getattr(rider, "rider", None)
    if not profile or profile.status != RiderProfile.Status.APPROVED:
        raise DomainError("Only approved riders can take deliveries.")

    with transaction.atomic():
        order.rider = rider
        order.status = Order.Status.ASSIGNED
        order.accepted_at = timezone.now()
        order.save(update_fields=["rider", "status", "accepted_at"])
        log_event(order, Order.Status.ASSIGNED, actor=actor, note=f"Assigned to {rider.name}")
    notify(rider, "New delivery assigned", f"{order.number} · {order.delivery_address}", Notification.Kind.ORDER)
    notify(
        order.customer,
        "Rider on the way",
        f"{rider.name} is heading to {order.station.name} to collect your fuel.",
        Notification.Kind.ORDER,
    )
    return order


def advance_order(order: Order, status: str, actor: User | None = None, note: str = "") -> Order:
    """Move an order forward one step (rider pickup → arrived → delivered)."""
    allowed = {
        Order.Status.PICKED_UP: {Order.Status.ASSIGNED},
        Order.Status.ARRIVED: {Order.Status.PICKED_UP},
        Order.Status.DELIVERED: {Order.Status.ARRIVED, Order.Status.PICKED_UP},
    }
    if status not in allowed or order.status not in allowed[status]:
        raise DomainError(f"Cannot move {order.number} from {order.status} to {status}.")

    now = timezone.now()
    stamp = {
        Order.Status.PICKED_UP: "picked_up_at",
        Order.Status.ARRIVED: "arrived_at",
        Order.Status.DELIVERED: "delivered_at",
    }[status]

    with transaction.atomic():
        order.status = status
        setattr(order, stamp, now)
        if status == Order.Status.DELIVERED:
            order.payment_status = Order.PaymentStatus.PAID
        order.save(update_fields=["status", stamp, "payment_status"])
        log_event(order, status, actor=actor, note=note)
        if status == Order.Status.DELIVERED:
            settle_delivery(order)
    return order


def settle_delivery(order: Order) -> None:
    """Rider earnings + platform commission + loyalty points, once per order."""
    if order.rider and not Transaction.objects.filter(order=order, kind=Transaction.Kind.EARNING).exists():
        record_transaction(
            user=order.rider,
            kind=Transaction.Kind.EARNING,
            amount=order.rider_pay,
            method="wallet",
            order=order,
            note=f"Delivery pay for {order.number}",
        )
        profile = getattr(order.rider, "rider", None)
        if profile:
            RiderProfile.objects.filter(pk=profile.pk).update(
                earnings_total=F("earnings_total") + order.rider_pay,
                deliveries_total=F("deliveries_total") + 1,
            )
        record_transaction(
            user=order.customer,
            kind=Transaction.Kind.COMMISSION,
            amount=order.service_fee,
            order=order,
            note=f"Platform fee for {order.number}",
        )

    if order.payment_method == Order.PaymentMethod.CASH and order.payment_status != Order.PaymentStatus.PAID:
        order.payment_status = Order.PaymentStatus.PAID
        order.save(update_fields=["payment_status"])

    points = order.total // 1000
    if points:
        User.objects.filter(pk=order.customer_id).update(points=F("points") + points)


def cancel_order(order: Order, reason: str, actor: User | None = None) -> Order:
    if not order.can_cancel:
        raise DomainError("This order is already on its way — contact support to cancel.")

    with transaction.atomic():
        # The fee is decided by the state *before* cancellation: once a rider
        # has collected the fuel, the cancellation fee applies.
        fee = FC["cancellation_fee"] if order.status == Order.Status.PICKED_UP else 0
        order.status = Order.Status.CANCELLED
        order.cancelled_at = timezone.now()
        order.cancel_reason = reason[:200]
        if order.payment_status == Order.PaymentStatus.PAID:
            order.payment_status = Order.PaymentStatus.REFUNDED
            credit_wallet(
                order.customer,
                order.total - fee,
                kind=Transaction.Kind.REFUND,
                order=order,
                note=f"Refund for {order.number}",
            )
        order.save(update_fields=["status", "cancelled_at", "cancel_reason", "payment_status"])
        log_event(order, Order.Status.CANCELLED, actor=actor, note=reason)

    notify(order.customer, "Order cancelled", f"{order.number} was cancelled. {reason}", Notification.Kind.ORDER)
    if order.rider:
        notify(order.rider, "Delivery cancelled", f"{order.number} was cancelled.", Notification.Kind.ORDER)
    return order


def rate_order(order: Order, rating: int, comment: str = "") -> Order:
    order.rating = max(1, min(5, int(rating)))
    order.review = comment[:400]
    order.save(update_fields=["rating", "review"])
    if order.rider:
        profile = getattr(order.rider, "rider", None)
        if profile:
            approved = Order.objects.filter(rider=order.rider, rating__isnull=False)
            avg = sum(o.rating for o in approved) / approved.count()
            RiderProfile.objects.filter(pk=profile.pk).update(rating=round(avg, 2))
    return order


def log_event(order: Order, status: str, *, actor=None, note="", when=None) -> OrderEvent:
    return OrderEvent.objects.create(order=order, status=status, actor=actor, note=note[:200], created_at=when or timezone.now())


def delivery_ping(order: Order, lat: float, lng: float, when=None):
    from .models import TrackingPing

    return TrackingPing.objects.create(order=order, rider=order.rider, lat=lat, lng=lng, created_at=when or timezone.now())


# --------------------------------------------------------------------------- messaging
def notify(user: User, title: str, body: str, kind=Notification.Kind.SYSTEM, when=None) -> Notification:
    return Notification.objects.create(user=user, title=title, body=body, kind=kind, created_at=when or timezone.now())


def send_otp_notification(user: User, code: str, purpose: str) -> dict:
    """Send a one-time code through the configured email backend."""
    if not user.email:
        return {"channel": None, "destination": None, "sent": False}
    labels = {
        OtpCode.Purpose.SIGNUP: ("Confirm your FuelOnDemand account", "account confirmation"),
        OtpCode.Purpose.LOGIN: ("Your FuelOnDemand sign-in code", "sign-in"),
        OtpCode.Purpose.RESET: ("Reset your FuelOnDemand password", "password reset"),
    }
    subject, reason = labels.get(purpose, ("Your FuelOnDemand verification code", "verification"))
    body = (
        f"Your FuelOnDemand {reason} code is {code}.\n\n"
        f"It expires in {FC['otp_ttl_seconds'] // 60} minutes. "
        "If you did not request this code, you can ignore this message."
    )
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)
    return {"channel": "email", "destination": user.email, "sent": True}


def audit(request, action: str, *, target="", severity=AuditEvent.Severity.INFO, actor=None, **meta) -> AuditEvent:
    user = actor or getattr(request, "user", None)
    return AuditEvent.objects.create(
        actor=user if user and getattr(user, "is_authenticated", False) else None,
        action=action,
        target=str(target)[:120],
        severity=severity,
        meta=meta,
        ip=client_ip(request) if request else None,
        user_agent=(request.META.get("HTTP_USER_AGENT", "")[:200] if request else ""),
    )


# --------------------------------------------------------------------------- OTP
def issue_otp(phone: str, purpose: str, *, respect_cooldown: bool = True) -> tuple[OtpCode, str]:
    recent = OtpCode.objects.filter(phone=phone, purpose=purpose).first()
    if respect_cooldown and recent and (timezone.now() - recent.created_at).total_seconds() < FC["otp_resend_seconds"]:
        raise DomainError(f"Please wait {FC['otp_resend_seconds']}s before requesting another code.")
    OtpCode.objects.filter(phone=phone, purpose=purpose, consumed_at__isnull=True).update(consumed_at=timezone.now())
    code = numeric_code(6)
    otp = OtpCode.objects.create(
        phone=phone,
        purpose=purpose,
        code_hash=make_password(code),
        expires_at=timezone.now() + timedelta(seconds=FC["otp_ttl_seconds"]),
    )
    return otp, code


def verify_otp(phone: str, purpose: str, code: str) -> bool:
    otp = OtpCode.objects.filter(phone=phone, purpose=purpose, consumed_at__isnull=True).first()
    if not otp or otp.expires_at < timezone.now() or otp.attempts >= FC["otp_max_attempts"]:
        return False
    if not check_password(code, otp.code_hash):
        OtpCode.objects.filter(pk=otp.pk).update(attempts=F("attempts") + 1)
        return False
    otp.consumed_at = timezone.now()
    otp.save(update_fields=["consumed_at"])
    return True


# --------------------------------------------------------------------------- riders
def set_rider_status(profile: RiderProfile, status: str, *, actor=None, reason="") -> RiderProfile:
    profile.status = status
    profile.reviewed_at = timezone.now()
    if actor:
        profile.reviewed_by = actor
    if status == RiderProfile.Status.REJECTED:
        profile.reject_reason = reason[:200]
    profile.save(update_fields=["status", "reviewed_at", "reviewed_by", "reject_reason"])
    verb = {"approved": "approved", "rejected": "rejected", "suspended": "suspended", "pending": "sent back for review"}[status]
    notify(profile.user, f"Application {verb}", reason[:200] or "Your rider application was updated.", Notification.Kind.SYSTEM)
    return profile


# --------------------------------------------------------------------------- prices
def set_price(station: Station, fuel_type: str, price: int, actor=None) -> "FuelPrice":
    from .models import FuelPrice

    price = int(price)
    if price <= 0 or price > 100_000:
        raise DomainError("Enter a fuel price between 1 and 100,000 UGX.")
    obj, created = FuelPrice.objects.get_or_create(
        station=station, fuel_type=fuel_type, defaults={"price": price}
    )
    if not created:
        obj.previous_price = obj.price
        obj.price = price
        obj.save(update_fields=["previous_price", "price", "updated_at"])
    return obj


# --------------------------------------------------------------------------- tankers
def _stock_for(station: Station, fuel_type: str) -> StationStock:
    stock, _ = StationStock.objects.get_or_create(
        station=station, fuel_type=fuel_type, defaults={"litres": 0, "capacity_litres": 30000}
    )
    return stock


def next_trip_reference() -> str:
    stamp = timezone.localtime().strftime("%y%m%d")
    for index in range(1, 1000):
        reference_code = f"TRP-{stamp}-{index:03d}"
        if not TankerTrip.objects.filter(reference=reference_code).exists():
            return reference_code
    return f"TRP-{stamp}-{TankerTrip.objects.count() + 1:03d}"


@transaction.atomic
def create_trip(
    *,
    tanker: Tanker,
    station: Station,
    fuel_type: str,
    litres: int,
    origin: str = "Kampala depot",
    notes: str = "",
    actor=None,
) -> TankerTrip:
    """Assign a bulk loading job to a truck and a destination station."""
    litres = int(litres or 0)
    if tanker.status == Tanker.Status.SUSPENDED:
        raise DomainError(f"{tanker.plate} is suspended and cannot take new jobs.")
    if litres <= 0:
        raise DomainError("Volume must be greater than zero.")
    if litres > tanker.capacity_litres:
        raise DomainError(f"{tanker.plate} carries at most {tanker.capacity_litres:,} L.")
    if tanker.trips.filter(status__in=TankerTrip.ACTIVE_STATUSES).exists():
        raise DomainError(f"{tanker.plate} already has an open trip. Close it first.")
    if tanker.driver_id and tanker.driver.is_suspended:
        raise DomainError(f"{tanker.driver.name} is suspended; assign another driver.")

    trip = TankerTrip.objects.create(
        reference=next_trip_reference(),
        tanker=tanker,
        driver=tanker.driver,
        station=station,
        fuel_type=fuel_type,
        assigned_litres=litres,
        origin=(origin or "Kampala depot")[:90],
        notes=(notes or "")[:200],
        created_by=actor,
    )
    audit(
        None,
        "trip.assigned",
        target=f"{trip.reference} {tanker.plate} to {station.name}",
        actor=actor,
        litres=litres,
        fuel=fuel_type,
    )
    return trip


def _trip_step(trip: TankerTrip, expected, new, stamp: str, action: str, actor=None, **meta) -> TankerTrip:
    if trip.status != expected:
        raise DomainError(
            f"{trip.reference} is {trip.get_status_display().lower()}; expected {expected.label.lower()}."
        )
    if new == TankerTrip.Status.CANCELLED and trip.status in {
        TankerTrip.Status.OFFLOADED,
        TankerTrip.Status.COMPLETED,
    }:
        raise DomainError("Fuel already offloaded; this trip can no longer be cancelled.")
    trip.status = new
    if stamp:
        setattr(trip, stamp, timezone.now())
    trip.save()
    audit(None, action, target=trip.reference, actor=actor, status=new.value, **meta)
    return trip


@transaction.atomic
def accept_trip(trip: TankerTrip, actor=None) -> TankerTrip:
    return _trip_step(trip, TankerTrip.Status.ASSIGNED, TankerTrip.Status.ACCEPTED, "accepted_at", "trip.accepted", actor)


@transaction.atomic
def load_trip(trip: TankerTrip, litres, actor=None) -> TankerTrip:
    """Driver records what was actually loaded at the depot."""
    try:
        litres = int(litres or 0)
    except (TypeError, ValueError):
        raise DomainError("Record the litres loaded as a number.")
    if litres <= 0:
        raise DomainError("Record the litres loaded.")
    if litres > trip.tanker.capacity_litres:
        raise DomainError(f"{trip.tanker.plate} carries at most {trip.tanker.capacity_litres:,} L.")
    if trip.status != TankerTrip.Status.ACCEPTED:
        raise DomainError(f"{trip.reference} must be accepted before loading.")
    trip.loaded_litres = litres
    trip.status = TankerTrip.Status.LOADED
    trip.loaded_at = timezone.now()
    trip.save()
    audit(None, "trip.loaded", target=trip.reference, actor=actor, litres=litres)
    return trip


@transaction.atomic
def depart_trip(trip: TankerTrip, actor=None) -> TankerTrip:
    return _trip_step(trip, TankerTrip.Status.LOADED, TankerTrip.Status.IN_TRANSIT, "departed_at", "trip.departed", actor)


@transaction.atomic
def arrive_trip(trip: TankerTrip, actor=None) -> TankerTrip:
    return _trip_step(trip, TankerTrip.Status.IN_TRANSIT, TankerTrip.Status.ARRIVED, "arrived_at", "trip.arrived", actor)


@transaction.atomic
def offload_trip(trip: TankerTrip, litres, actor=None) -> TankerTrip:
    """Station confirms the volume received; stock is credited and variance kept."""
    try:
        litres = int(litres or 0)
    except (TypeError, ValueError):
        raise DomainError("Record the litres received as a number.")
    loaded = trip.loaded_litres or trip.assigned_litres
    if litres <= 0 or litres > loaded:
        raise DomainError(f"Received volume must be between 1 and {loaded:,} L.")
    if trip.status != TankerTrip.Status.ARRIVED:
        raise DomainError(f"{trip.reference} has not arrived at {trip.station.name} yet.")

    stock = _stock_for(trip.station, trip.fuel_type)
    stock.litres = stock.litres + litres
    stock.save(update_fields=["litres", "updated_at"])

    trip.received_litres = litres
    trip.status = TankerTrip.Status.OFFLOADED
    trip.offloaded_at = timezone.now()
    trip.save()
    audit(
        None,
        "trip.offloaded",
        target=f"{trip.reference} {trip.station.name}",
        actor=actor,
        litres=litres,
        variance=(trip.loaded_litres or 0) - litres,
    )
    return trip


@transaction.atomic
def complete_trip(trip: TankerTrip, actor=None) -> TankerTrip:
    if trip.status != TankerTrip.Status.OFFLOADED:
        raise DomainError(f"{trip.reference} must be offloaded before it can be reconciled.")
    trip.status = TankerTrip.Status.COMPLETED
    trip.completed_at = timezone.now()
    trip.save()
    audit(
        None,
        "trip.reconciled",
        target=trip.reference,
        actor=actor,
        loaded=trip.loaded_litres,
        received=trip.received_litres,
        variance=trip.variance_litres,
        severity=AuditEvent.Severity.WARNING if trip.variance_litres else AuditEvent.Severity.INFO,
    )
    return trip


@transaction.atomic
def cancel_trip(trip: TankerTrip, actor=None, reason: str = "") -> TankerTrip:
    if trip.status in {TankerTrip.Status.OFFLOADED, TankerTrip.Status.COMPLETED}:
        raise DomainError("Fuel already offloaded; this trip can no longer be cancelled.")
    if trip.status == TankerTrip.Status.CANCELLED:
        raise DomainError("This trip is already cancelled.")
    trip.status = TankerTrip.Status.CANCELLED
    trip.save(update_fields=["status"])
    audit(None, "trip.cancelled", target=trip.reference, actor=actor, reason=(reason or "")[:120])
    return trip


@transaction.atomic
def set_tanker_status(tanker: Tanker, status: str, actor=None) -> Tanker:
    valid = {choice for choice, _label in Tanker.Status.choices}
    if status not in valid:
        raise DomainError("Unknown tanker status.")
    if status == Tanker.Status.SUSPENDED and tanker.trips.filter(
        status__in=TankerTrip.ACTIVE_STATUSES
    ).exists():
        raise DomainError("Close the open trip before suspending this truck.")
    tanker.status = status
    tanker.save(update_fields=["status", "updated_at"])
    audit(None, "tanker.status", target=tanker.plate, actor=actor, status=status)
    return tanker


# --------------------------------------------------------------------------- notifications
NOTIFICATION_AUDIENCES = {
    "customers": ("Customers", {"role": "customer"}),
    "riders": ("Riders", {"role": "rider"}),
    "tankers": ("Tanker drivers", {"role": "tanker"}),
    "stations": ("Station staff", {"role": "station"}),
    "everyone": ("Everyone", {}),
}


@transaction.atomic
def broadcast_notification(*, audience: str, kind: str, title: str, body: str, actor=None) -> int:
    """Push one message to a whole segment; returns how many inboxes it landed in."""
    if audience not in NOTIFICATION_AUDIENCES:
        raise DomainError("Choose who should receive this message.")
    title = (title or "").strip()
    body = (body or "").strip()
    if len(title) < 3:
        raise DomainError("Add a title of at least 3 characters.")
    if len(body) < 3:
        raise DomainError("Add a message of at least 3 characters.")
    if kind not in {choice for choice, _label in Notification.Kind.choices}:
        kind = Notification.Kind.SYSTEM

    label, filters = NOTIFICATION_AUDIENCES[audience]
    recipients = (
        User.objects.filter(is_active=True, is_suspended=False)
        .exclude(role=Role.STAFF)
        .filter(**filters)
    )
    rows = [
        Notification(user=user, kind=kind, title=title[:90], body=body[:240])
        for user in recipients
    ]
    Notification.objects.bulk_create(rows, batch_size=200)
    audit(
        None,
        "notification.broadcast",
        target=label,
        actor=actor,
        kind=kind,
        recipients=len(rows),
    )
    return len(rows)
