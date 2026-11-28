"""Aggregations behind the console: KPIs, chart series and the live pulse.

Every number here is computed from the database — no hard-coded dashboard
figures. Keeping the queries in one module makes them easy to test and reuse
between the server-rendered pages and the JSON polling endpoint.
"""
from __future__ import annotations

from datetime import timedelta

from django.db.models import Avg, Count, F, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from core.models import (
    Order,
    RiderProfile,
    Station,
    SupportTicket,
    Tanker,
    TankerTrip,
    Transaction,
    User,
)
from core.utils import compact_ugx, day_range, percent

PAID = Order.PaymentStatus.PAID
SLA_MINUTES = 60  # door-to-door window quoted to customers


def _delta(current: float, previous: float) -> float:
    if not previous:
        return 100.0 if current else 0.0
    return round(((current - previous) / previous) * 100, 1)


def revenue_for(day) -> int:
    return (
        Order.objects.filter(created_at__date=day, payment_status=PAID).aggregate(total=Sum("total"))["total"] or 0
    )


def on_time_rate(day) -> float | None:
    """Share of deliveries closed inside the quoted door-to-door window.

    A flat SLA keeps the figure readable for dispatch: an order is on time when
    it is handed over within SLA_MINUTES of being placed. Returns None when
    nothing was delivered that day, so the card can say "no data" honestly.
    """
    delivered = Order.objects.filter(
        status=Order.Status.DELIVERED, delivered_at__date=day, delivered_at__isnull=False
    ).only("created_at", "delivered_at")
    total = 0
    on_time = 0
    for order in delivered:
        total += 1
        if (order.delivered_at - order.created_at).total_seconds() <= SLA_MINUTES * 60:
            on_time += 1
    if not total:
        return None
    return round(on_time / total * 100, 1)


def kpis() -> dict:
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)

    orders_today = Order.objects.filter(created_at__date=today)
    orders_yesterday = Order.objects.filter(created_at__date=yesterday)
    revenue_today = revenue_for(today)
    revenue_yesterday = revenue_for(yesterday)

    delivered = Order.objects.filter(status=Order.Status.DELIVERED, delivered_at__date=today)
    avg_minutes = 0
    if delivered:
        gaps = [(o.delivered_at - o.created_at).total_seconds() / 60 for o in delivered if o.delivered_at]
        avg_minutes = int(sum(gaps) / len(gaps)) if gaps else 0

    active = Order.objects.filter(status__in=Order.ACTIVE_STATUSES).count()
    riders_online = RiderProfile.objects.filter(
        status=RiderProfile.Status.APPROVED, online=True
    ).count()
    riders_total = RiderProfile.objects.filter(status=RiderProfile.Status.APPROVED).count()

    new_customers = User.objects.filter(role="customer", date_joined__date=today).count()
    new_customers_prev = User.objects.filter(role="customer", date_joined__date=yesterday).count()

    refunds = Transaction.objects.filter(kind=Transaction.Kind.REFUND, created_at__date=today).aggregate(
        total=Sum("amount")
    )["total"] or 0

    completed_today = delivered.count()
    cancelled_today = Order.objects.filter(status=Order.Status.CANCELLED, cancelled_at__date=today).count()
    success_rate = round((completed_today / (completed_today + cancelled_today)) * 100, 1) if (completed_today + cancelled_today) else 100.0

    on_time_today = on_time_rate(today)
    on_time_yesterday = on_time_rate(yesterday)
    on_time_value = on_time_today if on_time_today is not None else 0.0

    approved_pending = RiderProfile.objects.filter(status=RiderProfile.Status.PENDING).count()
    open_tickets = SupportTicket.objects.filter(status=SupportTicket.Status.OPEN).count()
    failed_payments = Order.objects.filter(payment_status=Order.PaymentStatus.FAILED).count()
    delivered_yesterday = Order.objects.filter(
        status=Order.Status.DELIVERED, delivered_at__date=yesterday
    ).count()

    return {
        "revenue": {
            "value": revenue_today,
            "display": compact_ugx(revenue_today),
            "delta": _delta(revenue_today, revenue_yesterday),
            "hint": "vs yesterday",
        },
        "orders": {
            "value": orders_today.count(),
            "display": f"{orders_today.count():,}",
            "delta": _delta(orders_today.count(), orders_yesterday.count()),
            "hint": "vs yesterday",
        },
        "delivered": {
            "value": completed_today,
            "display": f"{completed_today:,}",
            "delta": _delta(completed_today, delivered_yesterday),
            "hint": "vs yesterday",
        },
        "active": {
            "value": active,
            "display": f"{active}",
            "delta": 0,
            "hint": "in progress right now",
        },
        "delivery_time": {
            "value": avg_minutes,
            "display": f"{avg_minutes} min",
            "delta": 0,
            "hint": "average door-to-door",
        },
        "riders": {
            "value": riders_online,
            "display": f"{riders_online}/{riders_total}",
            "delta": percent(riders_online, riders_total),
            "hint": "online vs approved",
        },
        "success": {
            "value": success_rate,
            "display": f"{success_rate:.0f}%",
            "delta": 0,
            "hint": "completion rate today",
        },
        "on_time": {
            "value": on_time_value,
            "display": f"{on_time_value:.0f}%",
            "delta": _delta(on_time_value, on_time_yesterday or 0),
            "hint": "inside the 60-min SLA",
            "tracked": on_time_today is not None,
        },
        "customers": {
            "value": new_customers,
            "display": f"{new_customers}",
            "delta": _delta(new_customers, new_customers_prev),
            "hint": "joined today",
        },
        "tankers": {
            "value": Tanker.objects.filter(status=Tanker.Status.ACTIVE).count(),
            "display": "%d/%d" % (
                Tanker.objects.filter(status=Tanker.Status.ACTIVE).count(),
                Tanker.objects.count(),
            ),
            "delta": 0,
            "hint": "on the road vs fleet",
            "trips": TankerTrip.objects.filter(status__in=TankerTrip.ACTIVE_STATUSES).count(),
        },
        "stations": {
            "value": Station.objects.filter(is_active=True).count(),
            "display": f"{Station.objects.filter(is_active=True).count()}",
            "delta": 0,
            "hint": "connected stations",
        },
        "refunds": {
            "value": refunds,
            "display": compact_ugx(refunds),
            "delta": 0,
            "hint": "refunded today",
        },
        "alerts": {
            "pending_riders": approved_pending,
            "open_tickets": open_tickets,
            "failed_payments": failed_payments,
            "total": approved_pending + open_tickets + failed_payments,
        },
    }


def revenue_series(days: int = 14) -> list[dict]:
    start = timezone.localdate() - timedelta(days=days - 1)
    paid = (
        Order.objects.filter(created_at__date__gte=start, payment_status=PAID)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(revenue=Sum("total"), orders=Count("id"))
    )
    placed = (
        Order.objects.filter(created_at__date__gte=start)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(orders=Count("id"))
    )
    revenue_by_day = {row["day"]: row["revenue"] for row in paid}
    orders_by_day = {row["day"]: row["orders"] for row in placed}

    series = []
    for day in day_range(days):
        series.append(
            {
                "date": day.isoformat(),
                "label": day.strftime("%d %b"),
                "revenue": revenue_by_day.get(day, 0) or 0,
                "orders": orders_by_day.get(day, 0) or 0,
            }
        )
    return series


def status_breakdown(days: int = 7) -> list[dict]:
    start = timezone.localdate() - timedelta(days=days - 1)
    rows = (
        Order.objects.filter(created_at__date__gte=start)
        .values("status")
        .annotate(count=Count("id"), revenue=Sum("total"))
        .order_by("-count")
    )
    labels = dict(Order.Status.choices)
    palette = {
        "delivered": "#55C68B",
        "cancelled": "#F36969",
        "confirmed": "#F5C72E",
        "assigned": "#7AB8FF",
        "picked_up": "#B48CFF",
        "arrived": "#5AD7D0",
        "pending_payment": "#8C9095",
    }
    return [
        {
            "label": labels.get(row["status"], row["status"]),
            "status": row["status"],
            "count": row["count"],
            "revenue": row["revenue"] or 0,
            "color": palette.get(row["status"], "#8C9095"),
        }
        for row in rows
    ]


def fuel_mix(days: int = 7) -> list[dict]:
    start = timezone.localdate() - timedelta(days=days - 1)
    rows = (
        Order.objects.filter(created_at__date__gte=start)
        .values("fuel_type")
        .annotate(count=Count("id"), litres=Sum("litres"), revenue=Sum("total"))
    )
    palette = {"petrol": "#F5C72E", "diesel": "#5AD7D0", "kerosene": "#B48CFF"}
    labels = {"petrol": "Petrol", "diesel": "Diesel", "kerosene": "Kerosene"}
    total = sum(row["count"] for row in rows) or 1
    return [
        {
            "label": labels.get(row["fuel_type"], row["fuel_type"]),
            "count": row["count"],
            "litres": float(row["litres"] or 0),
            "revenue": row["revenue"] or 0,
            "share": round(row["count"] / total * 100, 1),
            "color": palette.get(row["fuel_type"], "#8C9095"),
        }
        for row in sorted(rows, key=lambda r: r["count"], reverse=True)
    ]


def top_stations(days: int = 7, limit: int = 5) -> list[dict]:
    start = timezone.localdate() - timedelta(days=days - 1)
    rows = (
        Order.objects.filter(created_at__date__gte=start)
        .values("station__name", "station__brand")
        .annotate(orders=Count("id"), revenue=Sum("total"))
        .order_by("-revenue")[:limit]
    )
    best = rows[0]["revenue"] if rows else 1
    return [
        {
            "name": row["station__name"],
            "brand": row["station__brand"],
            "orders": row["orders"],
            "revenue": row["revenue"] or 0,
            "share": percent(row["revenue"] or 0, best),
        }
        for row in rows
    ]


def top_riders(limit: int = 5) -> list[dict]:
    rows = (
        Order.objects.filter(status=Order.Status.DELIVERED, rider__isnull=False)
        .values("rider__name", "rider__phone", "rider__rider__plate", "rider__rider__rating")
        .annotate(deliveries=Count("id"), payout=Sum("rider_pay"))
        .order_by("-deliveries")[:limit]
    )
    return [
        {
            "name": row["rider__name"],
            "phone": row["rider__phone"],
            "plate": row["rider__rider__plate"],
            "rating": row["rider__rider__rating"],
            "deliveries": row["deliveries"],
            "payout": row["payout"] or 0,
        }
        for row in rows
    ]


def payment_mix(days: int = 7) -> list[dict]:
    start = timezone.localdate() - timedelta(days=days - 1)
    rows = (
        Order.objects.filter(created_at__date__gte=start)
        .values("payment_method")
        .annotate(count=Count("id"), revenue=Sum("total"))
        .order_by("-count")
    )
    palette = {"momo": "#F5C72E", "airtel": "#F36969", "card": "#5AD7D0", "wallet": "#B48CFF", "cash": "#55C68B"}
    labels = dict(Order.PaymentMethod.choices)
    return [
        {
            "label": labels.get(row["payment_method"], row["payment_method"]),
            "count": row["count"],
            "revenue": row["revenue"] or 0,
            "color": palette.get(row["payment_method"], "#8C9095"),
        }
        for row in rows
    ]


def hourly_load() -> list[dict]:
    today = timezone.localdate()
    rows = (
        Order.objects.filter(created_at__date=today)
        .annotate(hour=_hour_expr())
        .values("hour")
        .annotate(count=Count("id"))
    )
    found = {row["hour"]: row["count"] for row in rows}
    return [{"hour": hour, "count": found.get(hour, 0)} for hour in range(0, 24)]


def _hour_expr():
    from django.db.models.functions import ExtractHour

    return ExtractHour("created_at")


def live_riders() -> list[dict]:
    profiles = RiderProfile.objects.select_related("user").filter(
        status=RiderProfile.Status.APPROVED, lat__isnull=False, lng__isnull=False
    )
    now = timezone.now()
    result = []
    for profile in profiles:
        active = Order.objects.filter(rider=profile.user, status__in=Order.ACTIVE_STATUSES).first()
        result.append(
            {
                "id": profile.user_id,
                "name": profile.user.name,
                "initials": profile.user.initials,
                "phone": profile.user.phone,
                "plate": profile.plate,
                "vehicle": profile.get_vehicle_type_display(),
                "online": profile.online,
                "lat": profile.lat,
                "lng": profile.lng,
                "rating": profile.rating,
                "deliveries": profile.deliveries_total,
                "earnings": profile.earnings_total,
                "last_seen": profile.last_seen_at.isoformat() if profile.last_seen_at else None,
                "stale": not profile.last_seen_at or (now - profile.last_seen_at).total_seconds() > 300,
                "order": active.number if active else None,
                "order_status": active.get_status_display() if active else None,
            }
        )
    return result


def active_orders(limit: int = 12) -> list[dict]:
    orders = (
        Order.objects.select_related("station", "customer", "rider")
        .filter(status__in=Order.ACTIVE_STATUSES)
        .order_by("-created_at")[:limit]
    )
    result = []
    for order in orders:
        result.append(
            {
                "id": order.pk,
                "number": order.number,
                "status": order.status,
                "status_label": order.get_status_display(),
                "customer": order.customer.name,
                "customer_initials": order.customer.initials,
                "rider": order.rider.name if order.rider else None,
                "rider_initials": order.rider.initials if order.rider else None,
                "station": order.station.name,
                "fuel": f"{order.litres} L {order.fuel_type}",
                "total": order.total,
                "address": order.delivery_address,
                "lat": order.lat,
                "lng": order.lng,
                "station_lat": order.station.lat,
                "station_lng": order.station.lng,
                "eta": order.eta_minutes,
                "created_at": order.created_at.isoformat(),
                "age_minutes": int((timezone.now() - order.created_at).total_seconds() // 60),
            }
        )
    return result


def recent_orders(limit: int = 8) -> list[dict]:
    orders = Order.objects.select_related("customer", "station", "rider").order_by("-created_at")[:limit]
    return [
        {
            "id": o.pk,
            "number": o.number,
            "customer": o.customer.name,
            "initials": o.customer.initials,
            "station": o.station.name,
            "fuel": f"{o.litres} L {o.fuel_type}",
            "total": o.total,
            "status": o.status,
            "status_label": o.get_status_display(),
            "method": o.get_payment_method_display(),
            "at": o.created_at.isoformat(),
        }
        for o in orders
    ]


def portfolio() -> dict:
    """Things the console shows in the right-hand insight rail."""
    week_ago = timezone.now() - timedelta(days=7)
    revenue = Order.objects.filter(payment_status=PAID).aggregate(total=Sum("total"))["total"] or 0
    commission = Order.objects.filter(payment_status=PAID).aggregate(total=Sum("service_fee"))["total"] or 0
    litres = Order.objects.filter(created_at__gte=week_ago).aggregate(total=Sum("litres"))["total"] or 0
    avg_order = Order.objects.filter(payment_status=PAID).aggregate(avg=Avg("total"))["avg"] or 0
    repeat = (
        User.objects.filter(role="customer", orders__isnull=False)
        .annotate(n=Count("orders"))
        .filter(n__gte=2)
        .count()
    )
    customers = User.objects.filter(role="customer").count()
    return {
        "revenue_total": revenue,
        "commission_total": commission,
        "litres_week": float(litres),
        "avg_order": int(avg_order),
        "repeat_rate": percent(repeat, customers),
        "customers": customers,
        "stations": Station.objects.filter(is_active=True).count(),
        "riders": RiderProfile.objects.filter(status=RiderProfile.Status.APPROVED).count(),
    }


def map_stations() -> list[dict]:
    return [
        {
            "id": station.slug,
            "name": station.name,
            "short": station.get_brand_display(),
            "brand_label": station.get_brand_display(),
            "address": station.address,
            "lat": station.lat,
            "lng": station.lng,
        }
        for station in Station.objects.filter(is_active=True)
    ]


def pulse() -> dict:
    """Everything the browser needs to refresh the console without a reload."""
    return {
        "kpis": kpis(),
        "feed": recent_orders(6),
        "orders": active_orders(8),
        "riders": live_riders(),
        "stations": map_stations(),
        "portfolio": portfolio(),
        "generated_at": timezone.now().isoformat(),
    }
