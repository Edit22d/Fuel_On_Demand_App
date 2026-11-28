"""Rider endpoints: application, availability, trip lifecycle, earnings."""
from __future__ import annotations

import functools
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.models import Notification, Order, OrderRejection, RiderProfile, Role, Transaction, User
from core.services import (
    DomainError,
    advance_order,
    assign_rider,
    delivery_ping,
    notify,
    record_transaction,
)
from core.utils import haversine_km, normalize_phone
from .security import decode_token, endpoint, fail, issue_token, ok, read_json, require_auth, require_method, throttle
from .serializers import notification_payload, order_payload, rider_payload, transaction_payload

FC = settings.FC


def rider_required(view):
    """A rider token *and* an approved application."""

    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        user = request.api_user
        profile = getattr(user, "rider", None)
        if not profile:
            return fail("This is not a rider account.", 403)
        if profile.status == RiderProfile.Status.SUSPENDED:
            return fail("Your rider account is suspended. Contact operations.", 403)
        if profile.status != RiderProfile.Status.APPROVED:
            return fail(f"Your rider application is {profile.get_status_display().lower()}.", 403)
        request.profile = profile
        return view(request, *args, **kwargs)

    return wrapper


@endpoint
def rider_register(request):
    if not require_method(request, "POST"):
        return fail("Method not allowed.", 405)
    data = read_json(request) or request.POST.dict()
    phone = normalize_phone(data.get("phone", ""))
    name = (data.get("name") or "").strip()
    password = data.get("password") or ""

    if User.objects.filter(phone=phone).exists():
        return fail("This number is already registered. Sign in instead.", 422, {"phone": ["Already registered."]})
    if len(name) < 2 or len(password) < 8:
        return fail("Enter your name and a password of at least 8 characters.", 422)

    throttle("rider-register", phone or "unknown", 5, 3600)
    with transaction.atomic():
        user = User.objects.create_user(phone=phone, password=password, name=name, role=Role.RIDER)
        RiderProfile.objects.create(
            user=user,
            status=RiderProfile.Status.PENDING,
            vehicle_type=data.get("vehicle_type", "boda"),
            plate=str(data.get("vehicle_registration", ""))[:16],
            national_id=str(data.get("national_id", ""))[:24],
            permit_number=str(data.get("permit_number", ""))[:24],
        )
    return ok({"message": "Application received. Our team reviews riders within 24 hours.",
               "status": "pending"}, status=201)


@endpoint
def rider_login(request):
    if not require_method(request, "POST"):
        return fail("Method not allowed.", 405)
    data = read_json(request)
    phone = normalize_phone(data.get("phone", ""))
    throttle("rider-login", f"{request.META.get('REMOTE_ADDR')}:{phone}", 10, 900)

    user = User.objects.filter(phone=phone, role=Role.RIDER).select_related("rider").first()
    if not user or not user.check_password(data.get("password", "")):
        return fail("That phone number or password is not correct.", 401)
    profile = getattr(user, "rider", None)
    if not profile:
        return fail("This account has no rider application.", 403)
    if profile.status != RiderProfile.Status.APPROVED:
        return fail(f"Your application is {profile.get_status_display().lower()}.", 403)

    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])
    return ok({"token": issue_token(user), "user": {"id": user.pk, "name": user.name, "role": user.role,
                                                   "rider": rider_payload(profile)}})


@endpoint
@require_auth(Role.RIDER)
@rider_required
def rider_status(request):
    if not require_method(request, "POST"):
        return fail("Method not allowed.", 405)
    profile = request.profile
    profile.online = bool(read_json(request).get("online", True))
    profile.last_seen_at = timezone.now()
    profile.save(update_fields=["online", "last_seen_at"])
    return ok({"online": profile.online})


@endpoint
@require_auth(Role.RIDER)
@rider_required
def rider_location(request):
    if not require_method(request, "POST"):
        return fail("Method not allowed.", 405)
    data = read_json(request)
    try:
        lat, lng = float(data["lat"]), float(data["lng"])
    except (KeyError, TypeError, ValueError):
        return fail("Send lat and lng.", 422)
    profile = request.profile
    profile.lat, profile.lng = lat, lng
    profile.last_seen_at = timezone.now()
    profile.save(update_fields=["lat", "lng", "last_seen_at"])

    active = Order.objects.filter(rider=request.api_user, status__in=[Order.Status.PICKED_UP, Order.Status.ARRIVED]).first()
    if active:
        delivery_ping(active, lat, lng)
    return ok({"message": "Location updated."})


@endpoint
@require_auth(Role.RIDER)
@rider_required
def rider_dashboard(request):
    if not require_method(request, "GET"):
        return fail("Method not allowed.", 405)
    profile = request.profile
    user = request.api_user
    today = timezone.localdate()
    delivered_today = Order.objects.filter(rider=user, status=Order.Status.DELIVERED, delivered_at__date=today)
    active = Order.objects.select_related("station", "customer").filter(rider=user, status__in=Order.ACTIVE_STATUSES).first()
    available = _available_orders(profile).count()

    return ok({"dashboard": {
        "online": profile.online,
        "rating": profile.rating,
        "wallet_balance": user.wallet_balance,
        "deliveries_today": delivered_today.count(),
        "earnings_today": sum(o.rider_pay for o in delivered_today),
        "deliveries_total": profile.deliveries_total,
        "earnings_total": profile.earnings_total,
        "available_count": available,
        "active_delivery": order_payload(active, with_tracking=True) if active else None,
    }})


def _available_orders(profile: RiderProfile):
    rejected = OrderRejection.objects.filter(rider=profile.user).values_list("order_id", flat=True)
    qs = Order.objects.select_related("station", "customer").filter(
        status=Order.Status.CONFIRMED, rider__isnull=True
    ).exclude(pk__in=rejected)
    if profile.lat is not None and profile.lng is not None:
        vehicle = profile.user.rider.vehicle_type
        max_km = {"boda": 7.0, "car": 12.0, "van": 15.0, "truck": 20.0}.get(vehicle, 8.0)
        ids = [o.pk for o in qs if haversine_km(profile.lat, profile.lng, o.station.lat, o.station.lng) <= max_km]
        qs = qs.filter(pk__in=ids)
    return qs


@endpoint
@require_auth(Role.RIDER)
@rider_required
def rider_deliveries(request):
    if not require_method(request, "GET"):
        return fail("Method not allowed.", 405)
    profile = request.profile
    sort = request.GET.get("sort", "nearest")
    orders = list(_available_orders(profile))

    def distance(order):
        if profile.lat is None or profile.lng is None:
            return 0
        return haversine_km(profile.lat, profile.lng, order.station.lat, order.station.lng)

    if sort == "pay":
        orders.sort(key=lambda o: o.rider_pay, reverse=True)
    elif sort == "shortest":
        orders.sort(key=lambda o: o.distance_km)
    else:
        orders.sort(key=distance)

    return ok({"deliveries": [order_payload(o) for o in orders],
               "count": len(orders)})


@endpoint
@require_auth(Role.RIDER)
@rider_required
def rider_delivery_detail(request, pk):
    if not require_method(request, "GET"):
        return fail("Method not allowed.", 405)
    order = Order.objects.select_related("station", "customer").filter(pk=pk, rider__isnull=True).first()
    if not order:
        return fail("This delivery is no longer available.", 404)
    return ok({"delivery": order_payload(order)})


@endpoint
@require_auth(Role.RIDER)
@rider_required
def rider_delivery_accept(request, pk):
    if not require_method(request, "POST"):
        return fail("Method not allowed.", 405)
    profile = request.profile
    if Order.objects.filter(rider=request.api_user, status__in=Order.ACTIVE_STATUSES).exists():
        return fail("Finish your current delivery before accepting another.", 409)
    with transaction.atomic():
        order = Order.objects.select_for_update().filter(pk=pk, status=Order.Status.CONFIRMED, rider__isnull=True).first()
        if not order:
            return fail("Another rider just took this delivery.", 409)
        assign_rider(order, request.api_user, actor=request.api_user)
    return ok({"delivery": order_payload(order), "message": "Delivery accepted."})


@endpoint
@require_auth(Role.RIDER)
@rider_required
def rider_delivery_reject(request, pk):
    if not require_method(request, "POST"):
        return fail("Method not allowed.", 405)
    order = Order.objects.filter(pk=pk, rider__isnull=True).first()
    if not order:
        return fail("Delivery not found.", 404)
    OrderRejection.objects.get_or_create(order=order, rider=request.api_user,
                                         defaults={"reason": str(read_json(request).get("reason", ""))[:160]})
    return ok({"message": "Delivery skipped."})


@endpoint
@require_auth(Role.RIDER)
@rider_required
def rider_active(request):
    if not require_method(request, "GET"):
        return fail("Method not allowed.", 405)
    order = Order.objects.select_related("station", "customer").filter(
        rider=request.api_user, status__in=Order.ACTIVE_STATUSES
    ).first()
    return ok({"delivery": order_payload(order, with_tracking=True) if order else None})


@endpoint
@require_auth(Role.RIDER)
@rider_required
def rider_pickup(request, pk):
    if not require_method(request, "POST"):
        return fail("Method not allowed.", 405)
    order = Order.objects.filter(pk=pk, rider=request.api_user).first()
    if not order:
        return fail("Delivery not found.", 404)
    code = str(read_json(request).get("code", ""))
    if code != order.pickup_code:
        return fail("That pickup code is not correct. Ask the attendant to confirm.", 422, {"code": ["Incorrect."]})
    advance_order(order, Order.Status.PICKED_UP, actor=request.api_user, note="Collected from station")
    notify(order.customer, "Fuel collected", f"Your rider left {order.station.name} with your fuel.", Notification.Kind.ORDER)
    return ok({"delivery": order_payload(order), "message": "Pickup confirmed."})


@endpoint
@require_auth(Role.RIDER)
@rider_required
def rider_arrived(request, pk):
    if not require_method(request, "POST"):
        return fail("Method not allowed.", 405)
    order = Order.objects.filter(pk=pk, rider=request.api_user).first()
    if not order:
        return fail("Delivery not found.", 404)
    advance_order(order, Order.Status.ARRIVED, actor=request.api_user, note="Rider arrived")
    notify(order.customer, "Rider has arrived", "Share your 4-digit delivery code to finish.", Notification.Kind.ORDER)
    return ok({"delivery": order_payload(order), "message": "Customer notified."})


@endpoint
@require_auth(Role.RIDER)
@rider_required
def rider_deliver(request, pk):
    if not require_method(request, "POST"):
        return fail("Method not allowed.", 405)
    order = Order.objects.filter(pk=pk, rider=request.api_user).first()
    if not order:
        return fail("Delivery not found.", 404)
    data = read_json(request) or request.POST.dict()
    if str(data.get("code", "")) != order.delivery_code:
        return fail("That delivery code is not correct.", 422, {"code": ["Incorrect."]})
    advance_order(order, Order.Status.DELIVERED, actor=request.api_user, note="Delivered with code")
    return ok({"delivery": order_payload(order), "message": "Delivery complete. Earnings credited."})


@endpoint
@require_auth(Role.RIDER)
@rider_required
def rider_earnings(request):
    if not require_method(request, "GET"):
        return fail("Method not allowed.", 405)
    profile = request.profile
    today = timezone.localdate()
    earnings = Transaction.objects.filter(user=request.api_user, kind=Transaction.Kind.EARNING)
    return ok({"earnings": {
        "today": sum(t.amount for t in earnings.filter(created_at__date=today)),
        "this_week": sum(t.amount for t in earnings.filter(created_at__gte=timezone.now() - timedelta(days=7))),
        "total": profile.earnings_total,
        "wallet_balance": request.api_user.wallet_balance,
        "payouts": [transaction_payload(t) for t in earnings[:20]],
        "commission_pct": profile.commission_pct,
    }})


@endpoint
@require_auth(Role.RIDER)
@rider_required
def rider_withdraw(request):
    if not require_method(request, "POST"):
        return fail("Method not allowed.", 405)
    data = read_json(request)
    try:
        amount = int(data.get("amount", 0))
    except (TypeError, ValueError):
        amount = 0
    method = data.get("method", "momo")
    if method not in {"momo", "airtel"}:
        return fail("Choose MTN MoMo or Airtel Money.", 422, {"method": ["Unsupported."]})
    user = request.api_user
    if amount < 5000:
        return fail("Minimum withdrawal is UGX 5,000.", 422, {"amount": ["Too small."]})
    if amount > user.wallet_balance:
        return fail("Your wallet balance is too low for this withdrawal.", 422, {"amount": ["Insufficient."]})
    User.objects.filter(pk=user.pk).update(wallet_balance=user.wallet_balance - amount)
    record_transaction(user=user, kind=Transaction.Kind.PAYOUT, amount=-amount, method=method,
                       note=f"Withdrawal to {method.upper()}")
    return ok({"message": "Withdrawal queued. You will receive the money shortly.",
               "balance": user.wallet_balance - amount})


# --------------------------------------------------------------------------- webhook
@endpoint
def payment_webhook(request, provider):
    if not require_method(request, "POST"):
        return fail("Method not allowed.", 405)
    secret = request.headers.get("X-Webhook-Secret", "")
    expected = settings.SECRET_KEY[-20:]
    if secret != expected:
        return fail("Invalid webhook secret.", 401)

    data = read_json(request)
    reference_value = str(data.get("reference", ""))
    status = data.get("status", "successful")
    order = Order.objects.filter(payment_reference=reference_value).first()
    if not order:
        return fail("Unknown payment reference.", 404)

    if status == "successful":
        from core.services import confirm_order

        order.payment_status = Order.PaymentStatus.PAID
        order.save(update_fields=["payment_status"])
        confirm_order(order)
        return ok({"message": "Payment confirmed."})

    order.payment_status = Order.PaymentStatus.FAILED
    order.save(update_fields=["payment_status"])
    return ok({"message": "Payment marked failed."})
