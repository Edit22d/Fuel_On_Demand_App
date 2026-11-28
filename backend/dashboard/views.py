"""Console shell: sign-in, overview, live ops board, pulse JSON, search, errors."""
from __future__ import annotations

import json
from urllib.parse import urlparse

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.core.cache import cache
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from core.models import AuditEvent, Order, RiderProfile, Station, SupportTicket, Transaction, User
from core.services import audit, get_setting
from core.utils import client_ip, normalize_phone

from . import analytics
from .decorators import console_required

FAIL_LIMIT = settings.CONSOLE_MAX_FAILURES
LOCK_SECONDS = settings.CONSOLE_LOCKOUT_SECONDS


def _safe_next(request, fallback: str) -> str:
    candidate = request.POST.get("next") or request.GET.get("next") or ""
    if candidate and url_has_allowed_host_and_scheme(candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return candidate
    return fallback


def _lock_key(identifier: str, request) -> str:
    return f"console-lock:{identifier.lower()}:{client_ip(request)}"


# --------------------------------------------------------------------------- auth
def login_view(request):
    if request.user.is_authenticated and request.user.can_use_console:
        return redirect("console:overview")

    error = None
    identifier = ""
    if request.method == "POST":
        identifier = (request.POST.get("identifier") or "").strip()
        password = request.POST.get("password") or ""
        lock_key = _lock_key(identifier, request)
        locked_for = cache.get(lock_key)
        if locked_for:
            error = f"Too many failed attempts. Try again in {max(1, locked_for // 60)} minutes."
        else:
            user = User.objects.filter(
                Q(email__iexact=identifier) | Q(phone=normalize_phone(identifier))
            ).first()
            if user and user.check_password(password) and user.can_use_console:
                auth_login(request, user)
                request.session.cycle_key()
                cache.delete(f"console-fail:{identifier.lower()}:{client_ip(request)}")
                audit(request, "console.login", target=user.email or user.phone, severity=AuditEvent.Severity.INFO)
                messages.success(request, f"Signed in as {user.first_name}. Session expires after 30 minutes idle.")
                return redirect(_safe_next(request, reverse("console:overview")))

            fail_key = f"console-fail:{identifier.lower()}:{client_ip(request)}"
            failures = cache.get(fail_key, 0) + 1
            cache.set(fail_key, failures, LOCK_SECONDS)
            if failures >= FAIL_LIMIT:
                cache.set(lock_key, LOCK_SECONDS, LOCK_SECONDS)
                cache.delete(fail_key)
                audit(
                    None,
                    "console.lockout",
                    target=identifier,
                    severity=AuditEvent.Severity.CRITICAL,
                    ip=client_ip(request),
                    attempts=failures,
                )
                error = "Account locked for 15 minutes after repeated failures."
            else:
                audit(
                    None,
                    "console.login_failed",
                    target=identifier,
                    severity=AuditEvent.Severity.WARNING,
                    ip=client_ip(request),
                    attempts=failures,
                )
                remaining = FAIL_LIMIT - failures
                error = f"Those credentials don't match an operations account. {remaining} attempt(s) left."

    return render(
        request,
        "dashboard/login.html",
        {
            "error": error,
            "identifier": identifier,
            "next": _safe_next(request, ""),
            "stats": _login_stats(),
        },
    )


def _login_stats() -> dict:
    today = timezone.localdate()
    return {
        "orders_today": Order.objects.filter(created_at__date=today).count(),
        "riders_online": RiderProfile.objects.filter(status=RiderProfile.Status.APPROVED, online=True).count(),
        "stations": Station.objects.filter(is_active=True).count(),
    }


@require_POST
def logout_view(request):
    audit(request, "console.logout", target=getattr(request.user, "email", ""))
    auth_logout(request)
    messages.info(request, "You have been signed out.")
    return redirect("console:login")


# --------------------------------------------------------------------------- overview
OVERVIEW_WINDOWS = {7: "This week", 14: "Last 14 days", 30: "This month"}
PERIOD_LABELS = {7: "7d", 14: "14d", 30: "30d"}


def _overview_days(request) -> int:
    try:
        days = int(request.GET.get("days") or 14)
    except (TypeError, ValueError):
        days = 14
    return days if days in OVERVIEW_WINDOWS else 14


@console_required
def overview(request):
    days = _overview_days(request)
    kpi = analytics.kpis()
    series = analytics.revenue_series(days)
    statuses = analytics.status_breakdown(7)
    fuel = analytics.fuel_mix(7)
    stations = analytics.top_stations(5)
    riders = analytics.top_riders(5)
    payments = analytics.payment_mix(7)
    portfolio = analytics.portfolio()
    live_orders = analytics.active_orders(6)
    live_riders = analytics.live_riders()

    best_day = max(series, key=lambda row: row["revenue"]) if series else {"label": "—", "revenue": 0}
    summary = {
        "avg_daily": int(sum(row["revenue"] for row in series) / len(series)) if series else 0,
        "best_label": best_day["label"],
        "best_revenue": best_day["revenue"],
        "orders_total": sum(row["orders"] for row in series),
        "avg_order": (sum(row["revenue"] for row in series) // max(1, sum(row["orders"] for row in series))),
    }
    status_total = sum(row["count"] for row in statuses) or 1
    payment_total = sum(row["count"] for row in payments) or 1

    chart_max = max((row["revenue"] for row in series), default=0) or 1
    for row in series:
        row["pct"] = round(row["revenue"] / chart_max * 100)

    revenue_total = sum(row["revenue"] for row in series)
    previous_total = sum(row["revenue"] for row in analytics.revenue_series(days * 2)[:days])
    summary["revenue_total"] = revenue_total
    summary["revenue_delta"] = (
        round((revenue_total - previous_total) / previous_total * 100, 1)
        if previous_total else (100.0 if revenue_total else 0.0)
    )

    now = timezone.localtime() if settings.USE_TZ else timezone.now()
    greeting = "Good morning" if now.hour < 12 else "Good afternoon" if now.hour < 17 else "Good evening"
    first_name = (request.user.first_name or request.user.name or "there").split(" ")[0]

    failed_payments = kpi["alerts"]["failed_payments"]
    payout = get_setting("payout_schedule", "Weekly, every Friday")
    automation = [
        {
            "title": "Rider auto-dispatch",
            "meta": f"{kpi['riders']['value']} riders eligible",
            "state": "Running",
            "on": True,
            "icon": "route",
            "tone": "tone-blue",
            "url": reverse("console:live"),
        },
        {
            "title": "Route optimisation",
            "meta": f"{kpi['active']['value']} deliveries in flight",
            "state": "Running",
            "on": True,
            "icon": "map",
            "tone": "tone-teal",
            "url": reverse("console:live"),
        },
        {
            "title": "Payment reconciliation",
            "meta": f"{failed_payments} need review" if failed_payments else "All collections matched",
            "state": "Needs review" if failed_payments else "Running",
            "on": not failed_payments,
            "icon": "payments",
            "tone": "tone-rose" if failed_payments else "tone-green",
            "url": reverse("console:payments"),
        },
        {
            "title": "Rider payouts",
            "meta": payout,
            "state": "Scheduled",
            "on": True,
            "icon": "wallet",
            "tone": "tone-gold",
            "url": reverse("console:reports"),
        },
    ]

    context = {
        "active_nav": "overview",
        "page_title": "Overview",
        "page_eyebrow": "Operations control centre",
        "greeting": greeting,
        "first_name": first_name,
        "today_label": now.strftime("%a, %d %b %Y"),
        "days": days,
        "period_label": OVERVIEW_WINDOWS[days],
        "period_options": [
            {"key": key, "label": PERIOD_LABELS[key], "on": key == days} for key in OVERVIEW_WINDOWS
        ],
        "kpi": kpi,
        "automation": automation,
        "portfolio": portfolio,
        "chart_series": series,
        "chart_statuses": statuses,
        "chart_fuel": fuel,
        "chart_stations": stations,
        "chart_payments": payments,
        "summary": summary,
        "status_total": status_total,
        "payment_total": payment_total,
        "top_riders": riders,
        "live": live_orders,
        "riders": live_riders,
        "feed": analytics.recent_orders(7),
        "spark": [row["revenue"] for row in series],
        "map_seed": json.dumps(
            {"stations": analytics.map_stations(), "riders": live_riders, "orders": live_orders}
        ),
        "announcement": get_setting("announcement", ""),
        "pending_riders": RiderProfile.objects.select_related("user").filter(
            status=RiderProfile.Status.PENDING
        )[:4],
        "open_tickets": SupportTicket.objects.select_related("customer").filter(
            status=SupportTicket.Status.OPEN
        )[:4],
        "recent_tx": Transaction.objects.select_related("user").order_by("-created_at")[:6],
        "json_series": json.dumps(series),
        "json_statuses": json.dumps(statuses),
        "json_fuel": json.dumps(fuel),
        "json_stations": json.dumps(stations),
        "json_payments": json.dumps(payments),
    }
    return render(request, "dashboard/overview.html", context)


@console_required
def live(request):
    riders = analytics.live_riders()
    orders = analytics.active_orders(20)
    stations = analytics.map_stations()
    alerts = analytics.kpis()["alerts"]
    return render(
        request,
        "dashboard/live.html",
        {
            "active_nav": "live",
            "page_title": "Live operations",
            "page_eyebrow": "Real-time dispatch board",
            "riders": riders,
            "online_riders": sum(1 for rider in riders if rider["online"]),
            "unassigned": sum(1 for order in orders if not order["rider"]),
            "orders": orders,
            "stations": stations,
            "map_seed": json.dumps({"stations": stations, "riders": riders, "orders": orders}),
            "horizon": alerts,
            "kpi": analytics.kpis(),
        },
    )


@console_required
def api_pulse(request):
    if request.method != "GET":
        return JsonResponse({"message": "Method not allowed."}, status=405)
    return JsonResponse(analytics.pulse(), safe=False)


@console_required
def api_search(request):
    term = (request.GET.get("q") or "").strip()
    if len(term) < 2:
        return JsonResponse({"results": []})
    results = []

    for order in Order.objects.select_related("customer").filter(
        Q(number__icontains=term) | Q(customer__name__icontains=term) | Q(customer__phone__icontains=term)
    )[:5]:
        results.append({"type": "Order", "label": order.number, "hint": f"{order.customer.name} · {order.get_status_display()}",
                        "url": reverse("console:order_detail", args=[order.pk])})
    for user in User.objects.filter(role="customer").filter(Q(name__icontains=term) | Q(phone__icontains=term))[:4]:
        results.append({"type": "Customer", "label": user.name, "hint": user.phone,
                        "url": reverse("console:customer_detail", args=[user.pk])})
    for user in User.objects.filter(role="rider").filter(Q(name__icontains=term) | Q(phone__icontains=term))[:4]:
        results.append({"type": "Rider", "label": user.name, "hint": user.phone,
                        "url": reverse("console:rider_detail", args=[user.pk])})
    for station in Station.objects.filter(Q(name__icontains=term) | Q(address__icontains=term))[:3]:
        results.append({"type": "Station", "label": station.name, "hint": station.address,
                        "url": reverse("console:stations") + f"#{station.slug}"})
    return JsonResponse({"results": results})


# --------------------------------------------------------------------------- errors
def error_403(request, exception=None):
    return render(request, "dashboard/403.html", status=403)


def error_404(request, exception=None):
    return render(request, "dashboard/404.html", status=404)


def error_500(request):
    return render(request, "dashboard/500.html", status=500)
