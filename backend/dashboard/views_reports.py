"""Reports & analytics: period-scoped trading report, network performance, fuel reconciliation.

Everything is computed from the database — the daily/monthly report, the CSV
export and the tanker reconciliation all read the same `_rows()` helper so the
screen and the download can never disagree.
"""
from __future__ import annotations

import csv
from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from core.models import Order, TankerTrip

from . import analytics
from .decorators import console_required

PAID = Order.PaymentStatus.PAID
PERIODS = [
    ("today", "Daily", 1),
    ("7d", "Weekly", 7),
    ("30d", "Monthly", 30),
    ("90d", "Quarterly", 90),
]
PERIOD_MAP = {key: (label, days) for key, label, days in PERIODS}


def _resolve(request):
    key = request.GET.get("period") or "7d"
    if key not in PERIOD_MAP:
        key = "7d"
    label, days = PERIOD_MAP[key]
    start = timezone.localdate() - timedelta(days=days - 1)
    return key, label, days, start


def _rows(start) -> list[dict]:
    """One row per calendar day: orders placed, delivered, revenue and litres."""
    placed = (
        Order.objects.filter(created_at__date__gte=start)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(
            orders=Count("id"),
            delivered=Count("id", filter=Q(status=Order.Status.DELIVERED)),
            cancelled=Count("id", filter=Q(status=Order.Status.CANCELLED)),
        )
    )
    paid = (
        Order.objects.filter(created_at__date__gte=start, payment_status=PAID)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(revenue=Sum("total"), litres=Sum("litres"), fees=Sum("delivery_fee"), pay=Sum("rider_pay"))
    )
    by_placed = {row["day"]: row for row in placed}
    by_paid = {row["day"]: row for row in paid}

    rows = []
    for offset in range((timezone.localdate() - start).days + 1):
        day = start + timedelta(days=offset)
        p = by_placed.get(day, {})
        m = by_paid.get(day, {})
        orders = p.get("orders", 0) or 0
        revenue = m.get("revenue", 0) or 0
        rows.append({
            "date": day,
            "label": day.strftime("%d %b"),
            "weekday": day.strftime("%a"),
            "orders": orders,
            "delivered": p.get("delivered", 0) or 0,
            "cancelled": p.get("cancelled", 0) or 0,
            "revenue": revenue,
            "litres": float(m.get("litres") or 0),
            "fees": m.get("fees", 0) or 0,
            "pay": m.get("pay", 0) or 0,
            "avg_order": round(revenue / orders) if orders else 0,
        })
    return rows


def _summary(rows: list[dict]) -> dict:
    orders = sum(r["orders"] for r in rows)
    revenue = sum(r["revenue"] for r in rows)
    litres = sum(r["litres"] for r in rows)
    delivered = sum(r["delivered"] for r in rows)
    cancelled = sum(r["cancelled"] for r in rows)
    closed = delivered + cancelled
    return {
        "orders": orders,
        "revenue": revenue,
        "litres": litres,
        "delivered": delivered,
        "cancelled": cancelled,
        "avg_order": round(revenue / orders) if orders else 0,
        "fees": sum(r["fees"] for r in rows),
        "rider_pay": sum(r["pay"] for r in rows),
        "completion": round(delivered / closed * 100, 1) if closed else 0.0,
        "daily_avg": round(revenue / max(1, len(rows))),
        "best": max(rows, key=lambda r: r["revenue"]) if rows else None,
    }


def _reconciliation(start) -> list[dict]:
    """Bulk fuel: what left the depot vs what the station signed for."""
    trips = (
        TankerTrip.objects.filter(
            status=TankerTrip.Status.COMPLETED, completed_at__date__gte=start
        )
        .values("station__name", "fuel_type")
        .annotate(trips=Count("id"), loaded=Sum("loaded_litres"), received=Sum("received_litres"))
        .order_by("-received")
    )
    rows = []
    for row in trips:
        loaded = row["loaded"] or 0
        received = row["received"] or 0
        rows.append({
            "station": row["station__name"],
            "fuel": row["fuel_type"],
            "trips": row["trips"],
            "loaded": loaded,
            "received": received,
            "variance": loaded - received,
            "variance_pct": round((loaded - received) / loaded * 100, 2) if loaded else 0.0,
        })
    return rows


@console_required
def reports(request):
    key, label, days, start = _resolve(request)
    rows = _rows(start)
    summary = _summary(rows)
    series = analytics.revenue_series(min(days, 90))
    series = [row for row in series if row["date"] >= start.isoformat()]
    fuel = analytics.fuel_mix(days)
    stations = analytics.top_stations(days, 6)
    riders = analytics.top_riders(6)
    payments = analytics.payment_mix(days)
    recon = _reconciliation(start)

    return render(request, "dashboard/reports.html", {
        "active_nav": "reports",
        "page_title": "Reports & analytics",
        "page_eyebrow": f"{label} trading report · {rows[0]['label']} – {rows[-1]['label']}",
        "periods": PERIODS,
        "period": key,
        "period_label": label,
        "days": days,
        "summary": summary,
        "rows": rows,
        "rows_desc": list(reversed(rows)),
        "chart_series": series,
        "chart_fuel": fuel,
        "chart_payments": payments,
        "payment_total": sum(p["count"] for p in payments) or 1,
        "stations": stations,
        "station_best": stations[0]["revenue"] if stations else 1,
        "riders": riders,
        "recon": recon,
        "recon_variance": sum(r["variance"] for r in recon),
        "recon_litres": sum(r["received"] for r in recon),
    })


@console_required
def reports_export(request):
    key, label, days, start = _resolve(request)
    rows = _rows(start)
    summary = _summary(rows)
    stamp = timezone.localdate().strftime("%Y%m%d")
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="fuelondemand-{key}-report-{stamp}.csv"'
    )
    writer = csv.writer(response)
    writer.writerow(["FuelOnDemand", f"{label} report", f"generated {timezone.now():%Y-%m-%d %H:%M}"])
    writer.writerow([])
    writer.writerow(["Revenue", summary["revenue"], "Orders", summary["orders"], "Litres", round(summary["litres"], 1)])
    writer.writerow(["Delivered", summary["delivered"], "Cancelled", summary["cancelled"], "Completion %", summary["completion"]])
    writer.writerow([])
    writer.writerow(["Date", "Weekday", "Orders", "Delivered", "Cancelled", "Litres", "Revenue", "Delivery fees", "Rider pay", "Avg order"])
    for row in rows:
        writer.writerow([
            row["date"].isoformat(), row["weekday"], row["orders"], row["delivered"], row["cancelled"],
            round(row["litres"], 1), row["revenue"], row["fees"], row["pay"], row["avg_order"],
        ])
    writer.writerow([])
    writer.writerow(["Bulk fuel reconciliation"])
    writer.writerow(["Station", "Fuel", "Trips", "Loaded (L)", "Received (L)", "Variance (L)", "Variance %"])
    for row in _reconciliation(start):
        writer.writerow([
            row["station"], row["fuel"], row["trips"], row["loaded"],
            row["received"], row["variance"], row["variance_pct"],
        ])
    return response