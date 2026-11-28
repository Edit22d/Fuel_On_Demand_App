"""Customer endpoints: stations, vehicles, places, orders, tracking, wallet."""
from __future__ import annotations

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from core.models import Order, Role, SavedPlace, Station, Transaction, Vehicle
from core.services import DomainError, cancel_order, create_order, credit_wallet, quote, rate_order
from core.utils import haversine_km, normalize_phone, reference
from .security import endpoint, fail, ok, read_json, require_auth, require_method
from .serializers import notification_payload, order_payload, station_payload, transaction_payload

FC = settings.FC


# --------------------------------------------------------------------------- stations
@endpoint
def stations(request):
    if not require_method(request, "GET"):
        return fail("Method not allowed.", 405)
    query = request.GET.get("q", "").strip()
    brand = request.GET.get("brand", "").strip()
    sort = request.GET.get("sort", "nearest")
    lat = request.GET.get("lat")
    lng = request.GET.get("lng")

    qs = Station.objects.filter(is_active=True).prefetch_related("prices")
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(address__icontains=query) | Q(brand__icontains=query))
    if brand:
        qs = qs.filter(brand=brand)

    payloads = [station_payload(s) for s in qs]
    if lat and lng:
        here = (float(lat), float(lng))
        for item in payloads:
            item["distance_km"] = haversine_km(here[0], here[1], item["lat"], item["lng"])
        if sort == "nearest":
            payloads.sort(key=lambda item: item["distance_km"])
    if sort == "price":
        payloads.sort(key=lambda item: item["prices"].get("petrol", 10**9))
    return ok({"stations": payloads})


@endpoint
def station_detail(request, slug):
    if not require_method(request, "GET"):
        return fail("Method not allowed.", 405)
    station = Station.objects.prefetch_related("prices").filter(slug=slug, is_active=True).first()
    if not station:
        return fail("Station not found.", 404)
    return ok({"station": station_payload(station)})


# --------------------------------------------------------------------------- garage
@endpoint
@require_auth(Role.CUSTOMER)
def vehicles(request):
    user = request.api_user
    if require_method(request, "GET"):
        return ok({"vehicles": [
            {"id": v.pk, "plate": v.plate, "make": v.make, "model": v.model,
             "fuel_class": v.fuel_class, "is_default": v.is_default}
            for v in user.vehicles.all()
        ]})
    if require_method(request, "POST"):
        data = read_json(request)
        if not (data.get("plate") or "").strip():
            return fail("Enter the number plate.", 422, {"plate": ["Required."]})
        vehicle = Vehicle.objects.create(
            owner=user,
            plate=str(data["plate"])[:16].upper(),
            make=str(data.get("make", ""))[:40],
            model=str(data.get("model", ""))[:40],
            fuel_class=data.get("fuel_class", "petrol"),
            is_default=bool(data.get("is_default")),
        )
        return ok({"vehicle": {"id": vehicle.pk, "plate": vehicle.plate}}, status=201)
    return fail("Method not allowed.", 405)


@endpoint
@require_auth(Role.CUSTOMER)
def vehicle_detail(request, pk):
    vehicle = Vehicle.objects.filter(pk=pk, owner=request.api_user).first()
    if not vehicle:
        return fail("Vehicle not found.", 404)
    if require_method(request, "DELETE"):
        vehicle.delete()
        return ok({"message": "Vehicle removed."})
    if require_method(request, "PUT", "PATCH"):
        data = read_json(request)
        for field in ("plate", "make", "model", "fuel_class"):
            if field in data:
                setattr(vehicle, field, str(data[field])[:40])
        vehicle.save()
        return ok({"message": "Vehicle updated."})
    return ok({"vehicle": {"id": vehicle.pk, "plate": vehicle.plate, "make": vehicle.make,
                           "model": vehicle.model, "fuel_class": vehicle.fuel_class}})


@endpoint
@require_auth(Role.CUSTOMER)
def places(request):
    user = request.api_user
    if require_method(request, "GET"):
        return ok({"places": [
            {"id": p.pk, "label": p.label, "address": p.address, "lat": p.lat, "lng": p.lng}
            for p in user.places.all()
        ]})
    if require_method(request, "POST"):
        data = read_json(request)
        place = SavedPlace.objects.create(
            owner=user,
            label=str(data.get("label", "Home"))[:40],
            address=str(data.get("address", ""))[:160],
            lat=float(data.get("lat") or 0.3476),
            lng=float(data.get("lng") or 32.5825),
        )
        return ok({"place": {"id": place.pk, "label": place.label}}, status=201)
    return fail("Method not allowed.", 405)


@endpoint
@require_auth(Role.CUSTOMER)
def place_detail(request, pk):
    place = SavedPlace.objects.filter(pk=pk, owner=request.api_user).first()
    if not place:
        return fail("Place not found.", 404)
    if require_method(request, "DELETE"):
        place.delete()
        return ok({"message": "Place removed."})
    if require_method(request, "PUT", "PATCH"):
        data = read_json(request)
        for field in ("label", "address"):
            if field in data:
                setattr(place, field, str(data[field])[:160])
        for field in ("lat", "lng"):
            if field in data:
                setattr(place, field, float(data[field]))
        place.save()
        return ok({"message": "Place updated."})
    return ok({"place": {"id": place.pk, "label": place.label, "address": place.address}})


# --------------------------------------------------------------------------- orders
@endpoint
@require_auth(Role.CUSTOMER)
def order_quote(request):
    if not require_method(request, "POST"):
        return fail("Method not allowed.", 405)
    data = read_json(request)
    station = Station.objects.filter(slug=data.get("station_id"), is_active=True).first()
    if not station:
        return fail("Choose a station first.", 422, {"station_id": ["Unknown station."]})
    result = quote(station, data.get("fuel_type", "petrol"), data.get("litres", 10),
                   data.get("delivery_lat"), data.get("delivery_lng"))
    return ok({"quote": result})


@endpoint
@require_auth(Role.CUSTOMER)
def orders(request):
    user = request.api_user
    if require_method(request, "GET"):
        scope = request.GET.get("scope", "active")
        qs = Order.objects.filter(customer=user).select_related("station", "rider", "rider__rider")
        qs = qs.filter(status__in=Order.ACTIVE_STATUSES) if scope == "active" else qs.exclude(status__in=Order.ACTIVE_STATUSES)
        return ok({"orders": [order_payload(o) for o in qs[:50]]})

    if require_method(request, "POST"):
        data = read_json(request)
        station = Station.objects.filter(slug=data.get("station_id"), is_active=True).first()
        if not station:
            return fail("Choose a station first.", 422, {"station_id": ["Unknown station."]})
        if not (data.get("delivery_address") or "").strip():
            return fail("Where should we deliver the fuel?", 422, {"delivery_address": ["Required."]})
        method = data.get("payment_method", "momo")
        aliases = {"mtn": "momo", "airtel_money": "airtel", "mobile": "momo"}
        method = aliases.get(method, method)
        if method not in dict(Order.PaymentMethod.choices):
            return fail("Choose a valid payment method.", 422, {"payment_method": ["Unsupported."]})

        order = create_order(
            customer=user,
            station=station,
            fuel_type=data.get("fuel_type", "petrol"),
            litres=data.get("litres", 10),
            payment_method=method,
            delivery_address=str(data["delivery_address"])[:200],
            lat=data.get("delivery_lat"),
            lng=data.get("delivery_lng"),
            note=str(data.get("delivery_note", ""))[:200],
            scheduled_at=None,
        )
        return ok({"order": order_payload(order, with_events=True)}, status=201)

    return fail("Method not allowed.", 405)


def _customer_order(request, pk, *, allow_statuses=None):
    order = Order.objects.select_related("station", "rider", "rider__rider").filter(pk=pk, customer=request.api_user).first()
    if not order:
        return None
    if allow_statuses and order.status not in allow_statuses:
        return None
    return order


@endpoint
@require_auth(Role.CUSTOMER)
def order_detail(request, pk):
    if not require_method(request, "GET"):
        return fail("Method not allowed.", 405)
    order = _customer_order(request, pk)
    if not order:
        return fail("Order not found.", 404)
    return ok({"order": order_payload(order, with_events=True)})


@endpoint
@require_auth(Role.CUSTOMER)
def order_tracking(request, pk):
    if not require_method(request, "GET"):
        return fail("Method not allowed.", 405)
    order = _customer_order(request, pk)
    if not order:
        return fail("Order not found.", 404)
    pings = [{"lat": p.lat, "lng": p.lng, "at": p.created_at.isoformat()} for p in order.pings.all()[:20]]
    return ok({"tracking": {
        "order": order_payload(order, with_tracking=True),
        "polyline": list(reversed(pings)),
        "status": order.status,
        "eta_minutes": order.eta_minutes,
        "server_time": timezone.now().isoformat(),
    }})


@endpoint
@require_auth(Role.CUSTOMER)
def order_cancel_preview(request, pk):
    if not require_method(request, "GET"):
        return fail("Method not allowed.", 405)
    order = _customer_order(request, pk)
    if not order:
        return fail("Order not found.", 404)
    picked_up = order.status in {Order.Status.PICKED_UP, Order.Status.ARRIVED}
    fee = FC["cancellation_fee"] if picked_up else 0
    return ok({"preview": {
        "can_cancel": order.can_cancel,
        "cancellation_fee": fee,
        "refund_amount": (order.total - fee) if order.payment_status == Order.PaymentStatus.PAID else 0,
        "message": (
            "Your rider already collected the fuel, so a cancellation fee applies."
            if picked_up else "You can cancel this order free of charge."
        ),
    }})


@endpoint
@require_auth(Role.CUSTOMER)
def order_cancel(request, pk):
    if not require_method(request, "POST"):
        return fail("Method not allowed.", 405)
    order = _customer_order(request, pk)
    if not order:
        return fail("Order not found.", 404)
    reason = str(read_json(request).get("reason", "Cancelled by customer"))[:200]
    order = cancel_order(order, reason, actor=request.api_user)
    return ok({"order": order_payload(order, with_events=True), "message": "Order cancelled."})


@endpoint
@require_auth(Role.CUSTOMER)
def order_rate(request, pk):
    if not require_method(request, "POST"):
        return fail("Method not allowed.", 405)
    order = _customer_order(request, pk)
    if not order:
        return fail("Order not found.", 404)
    if order.status != Order.Status.DELIVERED:
        raise DomainError("You can rate an order once it has been delivered.")
    data = read_json(request)
    try:
        rating = int(data.get("rating", 0))
    except (TypeError, ValueError):
        rating = 0
    if rating not in range(1, 6):
        return fail("Choose a rating from 1 to 5.", 422, {"rating": ["1-5"]})
    rate_order(order, rating, str(data.get("comment", ""))[:400])
    return ok({"message": "Thanks for the feedback."})


# --------------------------------------------------------------------------- wallet
@endpoint
@require_auth(Role.CUSTOMER)
def wallet(request):
    if not require_method(request, "GET"):
        return fail("Method not allowed.", 405)
    user = request.api_user
    recent = user.transactions.all()[:5]
    return ok({"wallet": {
        "balance": user.wallet_balance,
        "points": user.points,
        "transactions": [transaction_payload(t) for t in recent],
    }})


@endpoint
@require_auth(Role.CUSTOMER)
def wallet_transactions(request):
    if not require_method(request, "GET"):
        return fail("Method not allowed.", 405)
    txs = request.api_user.transactions.all()[:100]
    return ok({"transactions": [transaction_payload(t) for t in txs]})


@endpoint
@require_auth(Role.CUSTOMER)
def wallet_topup(request):
    if not require_method(request, "POST"):
        return fail("Method not allowed.", 405)
    data = read_json(request)
    try:
        amount = int(data.get("amount", 0))
    except (TypeError, ValueError):
        amount = 0
    if amount < 1000 or amount > 2_000_000:
        return fail("Top-ups must be between UGX 1,000 and UGX 2,000,000.", 422, {"amount": ["Out of range."]})
    method = data.get("method", "momo")
    if method not in {"momo", "airtel", "card"}:
        return fail("Choose a valid top-up method.", 422, {"method": ["Unsupported."]})
    tx = credit_wallet(request.api_user, amount, kind=Transaction.Kind.TOPUP, note="Wallet top-up")
    return ok({"message": "Wallet topped up.", "balance": request.api_user.wallet_balance,
               "transaction": transaction_payload(tx)}, status=201)


# --------------------------------------------------------------------------- notifications
@endpoint
@require_auth(Role.CUSTOMER, Role.RIDER)
def notifications(request):
    if not require_method(request, "GET"):
        return fail("Method not allowed.", 405)
    notes = request.api_user.notifications.all()[:60]
    return ok({"notifications": [notification_payload(n) for n in notes],
               "unread": request.api_user.notifications.filter(read_at__isnull=True).count()})


@endpoint
@require_auth(Role.CUSTOMER, Role.RIDER)
def notification_read(request, pk):
    if not require_method(request, "POST"):
        return fail("Method not allowed.", 405)
    note = request.api_user.notifications.filter(pk=pk, read_at__isnull=True).first()
    if note:
        note.read_at = timezone.now()
        note.save(update_fields=["read_at"])
    return ok({"message": "Marked as read."})


@endpoint
@require_auth(Role.CUSTOMER, Role.RIDER)
def notifications_read_all(request):
    if not require_method(request, "POST"):
        return fail("Method not allowed.", 405)
    request.api_user.notifications.filter(read_at__isnull=True).update(read_at=timezone.now())
    return ok({"message": "All caught up."})
