"""Console workflows: orders, stations, riders, customers, money, support, settings.

Mutations are POST-only, CSRF protected (Django default) and every one writes an
AuditEvent so the security log tells the whole story.
"""
from __future__ import annotations

import csv
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from core.models import (
    AuditEvent,
    FuelPrice,
    Order,
    RiderProfile,
    Station,
    SupportTicket,
    Transaction,
    User,
)
from core.services import (
    DomainError,
    advance_order,
    assign_rider,
    audit,
    cancel_order,
    credit_wallet,
    set_price,
    set_rider_status,
    set_setting,
    get_setting,
)

from .decorators import console_required

PAGE_SIZE = 20


# --------------------------------------------------------------------------- helpers
def _paginate(request, queryset, per_page=PAGE_SIZE):
    page = Paginator(queryset, per_page).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return page, params.urlencode()


def _back(request, fallback: str):
    target = request.POST.get("next") or fallback
    if target.startswith("/console/"):
        return redirect(target)
    return redirect(fallback)


def _riders_available():
    return (
        User.objects.select_related("rider")
        .filter(role="rider", is_suspended=False, rider__status=RiderProfile.Status.APPROVED)
        .order_by("name")
    )


# --------------------------------------------------------------------------- orders
@console_required
def orders(request):
    qs = Order.objects.select_related("customer", "station", "rider")
    status = request.GET.get("status", "")
    query = request.GET.get("q", "").strip()
    station = request.GET.get("station", "")
    method = request.GET.get("method", "")
    day = request.GET.get("day", "")
    sort = request.GET.get("sort", "-created_at")

    if status == "active":
        qs = qs.filter(status__in=Order.ACTIVE_STATUSES)
    elif status == "unassigned":
        qs = qs.filter(status=Order.Status.CONFIRMED)
    elif status:
        qs = qs.filter(status=status)
    if station:
        qs = qs.filter(station__slug=station)
    if method:
        qs = qs.filter(payment_method=method)
    if day:
        qs = qs.filter(created_at__date=day)
    if query:
        qs = qs.filter(Q(number__icontains=query) | Q(customer__name__icontains=query) | Q(customer__phone__icontains=query))
    if sort in {"-created_at", "created_at", "-total", "total", "status"}:
        qs = qs.order_by(sort)

    totals = qs.aggregate(revenue=Sum("total"), count=Count("id"))
    page, querystring = _paginate(request, qs)

    return render(request, "dashboard/orders.html", {
        "active_nav": "orders",
        "page_title": "Orders",
        "page_eyebrow": f"{totals['count'] or 0} matching orders",
        "page": page,
        "querystring": querystring,
        "stations": Station.objects.all(),
        "statuses": Order.Status.choices,
        "methods": Order.PaymentMethod.choices,
        "filters": {"status": status, "q": query, "station": station, "method": method, "day": day, "sort": sort},
        "revenue": totals["revenue"] or 0,
        "counts": {
            "active": Order.objects.filter(status__in=Order.ACTIVE_STATUSES).count(),
            "today": Order.objects.filter(created_at__date=timezone.localdate()).count(),
            "unassigned": Order.objects.filter(status=Order.Status.CONFIRMED).count(),
        },
    })


@console_required
def order_detail(request, pk):
    order = get_object_or_404(
        Order.objects.select_related("customer", "station", "rider", "rider__rider"), pk=pk
    )
    return render(request, "dashboard/order_detail.html", {
        "active_nav": "orders",
        "page_title": order.number,
        "page_eyebrow": f"{order.station.name} · {order.get_status_display()}",
        "order": order,
        "events": order.events.select_related("actor").order_by("created_at"),
        "pings": order.pings.all()[:40],
        "transactions": order.transactions.select_related("user"),
        "riders": _riders_available(),
        "timeline": _order_timeline(order),
    })


def _order_timeline(order: Order) -> list[dict]:
    steps = [
        ("Placed", order.created_at, True),
        ("Payment", order.created_at if order.payment_status == Order.PaymentStatus.PAID else None, order.payment_status == Order.PaymentStatus.PAID),
        ("Rider assigned", order.accepted_at, bool(order.accepted_at)),
        ("Collected", order.picked_up_at, bool(order.picked_up_at)),
        ("Arrived", order.arrived_at, bool(order.arrived_at)),
        ("Delivered", order.delivered_at, bool(order.delivered_at)),
    ]
    if order.status == Order.Status.CANCELLED:
        steps.append(("Cancelled", order.cancelled_at, True))
    return [{"label": label, "at": at, "done": done} for label, at, done in steps]


@console_required
@require_POST
def order_assign(request, pk):
    order = get_object_or_404(Order, pk=pk)
    rider = get_object_or_404(User, pk=request.POST.get("rider_id"), role="rider")
    try:
        assign_rider(order, rider, actor=request.user)
        audit(request, "order.assigned", target=order.number, rider=rider.name)
        messages.success(request, f"{order.number} assigned to {rider.name}.")
    except DomainError as exc:
        messages.error(request, str(exc))
    return _back(request, reverse("console:order_detail", args=[pk]))


@console_required
@require_POST
def order_cancel(request, pk):
    order = get_object_or_404(Order, pk=pk)
    reason = (request.POST.get("reason") or "Cancelled by operations").strip()
    try:
        cancel_order(order, reason, actor=request.user)
        audit(request, "order.cancelled", target=order.number, reason=reason)
        messages.success(request, f"{order.number} cancelled. Refund queued where applicable.")
    except DomainError as exc:
        messages.error(request, str(exc))
    return _back(request, reverse("console:order_detail", args=[pk]))


@console_required
@require_POST
def order_advance(request, pk):
    order = get_object_or_404(Order, pk=pk)
    target = request.POST.get("status", "")
    try:
        advance_order(order, target, actor=request.user, note="Advanced from console")
        audit(request, f"order.{target}", target=order.number)
        messages.success(request, f"{order.number} moved to {order.get_status_display().lower()}.")
    except DomainError as exc:
        messages.error(request, str(exc))
    return _back(request, reverse("console:order_detail", args=[pk]))


@console_required
def orders_export(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="fuelondemand-orders.csv"'
    writer = csv.writer(response)
    writer.writerow(["Number", "Created", "Customer", "Phone", "Station", "Fuel", "Litres", "Total", "Status", "Payment", "Rider"])
    for order in Order.objects.select_related("customer", "station", "rider")[:5000]:
        writer.writerow([
            order.number, timezone.localtime(order.created_at).strftime("%Y-%m-%d %H:%M"),
            order.customer.name, order.customer.phone, order.station.name,
            order.fuel_type, order.litres, order.total, order.status, order.payment_status,
            order.rider.name if order.rider else "",
        ])
    return response


# --------------------------------------------------------------------------- stations
@console_required
def stations(request):
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        address = (request.POST.get("address") or "").strip()
        if not name or not address:
            messages.error(request, "Give the station a name and an address.")
        else:
            slug = slugify(name)[:40] or f"station-{Station.objects.count() + 1}"
            station, created = Station.objects.get_or_create(
                slug=slug,
                defaults={
                    "name": name[:90],
                    "brand": request.POST.get("brand") or Station.Brand.OTHER,
                    "address": address[:160],
                    "lat": float(request.POST.get("lat") or 0.3476),
                    "lng": float(request.POST.get("lng") or 32.5825),
                },
            )
            if created:
                audit(request, "station.created", target=station.name)
                messages.success(request, f"{station.name} added to the network.")
            else:
                messages.info(request, "A station with that name already exists.")
        return redirect("console:stations")

    week_ago = timezone.now() - timedelta(days=7)
    station_list = Station.objects.prefetch_related("prices").annotate(
        orders_7d=Count("orders", filter=Q(orders__created_at__gte=week_ago)),
        revenue_7d=Sum("orders__total", filter=Q(orders__created_at__gte=week_ago)),
    ).order_by("-is_active", "name")

    return render(request, "dashboard/stations.html", {
        "active_nav": "stations",
        "page_title": "Stations",
        "page_eyebrow": f"{station_list.count()} forecourts in the network",
        "stations": station_list,
        "fuel_types": FuelPrice.FuelType.choices,
        "brands": Station.Brand.choices,
        "announcement": get_setting("announcement", ""),
    })


@console_required
@require_POST
def station_prices(request, slug):
    station = get_object_or_404(Station, slug=slug)
    changed = []
    for fuel_type, _label in FuelPrice.FuelType.choices:
        raw = request.POST.get(f"price_{fuel_type}")
        if not raw:
            continue
        try:
            price = int(raw)
        except ValueError:
            continue
        current = station.price_for(fuel_type)
        if current == price:
            continue
        try:
            set_price(station, fuel_type, price, actor=request.user)
            changed.append(f"{fuel_type} → {price:,}")
        except DomainError as exc:
            messages.error(request, str(exc))
    if changed:
        audit(request, "price.updated", target=station.name, changes=changed)
        messages.success(request, f"{station.name}: " + ", ".join(changed))
    else:
        messages.info(request, "Prices unchanged.")
    return redirect("console:stations")


@console_required
@require_POST
def station_toggle(request, slug):
    station = get_object_or_404(Station, slug=slug)
    station.is_active = not station.is_active
    station.save(update_fields=["is_active"])
    audit(request, "station.toggled", target=station.name, active=station.is_active)
    messages.success(request, f"{station.name} is now {'open' if station.is_active else 'closed'}.")
    return redirect("console:stations")


# --------------------------------------------------------------------------- riders
@console_required
def riders(request):
    qs = RiderProfile.objects.select_related("user")
    status = request.GET.get("status", "")
    query = request.GET.get("q", "").strip()
    if status:
        qs = qs.filter(status=status)
    if query:
        qs = qs.filter(Q(user__name__icontains=query) | Q(user__phone__icontains=query) | Q(plate__icontains=query))
    qs = qs.order_by("-created_at")
    page, querystring = _paginate(request, qs, 15)

    return render(request, "dashboard/riders.html", {
        "active_nav": "riders",
        "page_title": "Riders",
        "page_eyebrow": "Fleet applications and performance",
        "page": page,
        "querystring": querystring,
        "filters": {"status": status, "q": query},
        "statuses": RiderProfile.Status.choices,
        "counts": {
            "approved": RiderProfile.objects.filter(status="approved").count(),
            "pending": RiderProfile.objects.filter(status="pending").count(),
            "online": RiderProfile.objects.filter(status="approved", online=True).count(),
        },
    })


@console_required
def rider_detail(request, pk):
    profile = get_object_or_404(RiderProfile.objects.select_related("user", "reviewed_by"), pk=pk)
    deliveries = Order.objects.select_related("customer", "station").filter(rider=profile.user)[:15]
    earnings = Transaction.objects.filter(user=profile.user, kind=Transaction.Kind.EARNING)[:10]
    return render(request, "dashboard/rider_detail.html", {
        "active_nav": "riders",
        "page_title": profile.user.name,
        "page_eyebrow": f"Rider · {profile.get_vehicle_type_display()}",
        "profile": profile,
        "rider": profile.user,
        "deliveries": deliveries,
        "earnings": earnings,
        "delivered_count": Order.objects.filter(rider=profile.user, status=Order.Status.DELIVERED).count(),
        "active_order": Order.objects.filter(rider=profile.user, status__in=Order.ACTIVE_STATUSES).first(),
    })


@console_required
@require_POST
def rider_action(request, pk):
    profile = get_object_or_404(RiderProfile, pk=pk)
    action = request.POST.get("action")
    reason = (request.POST.get("reason") or "").strip()
    mapping = {
        "approve": RiderProfile.Status.APPROVED,
        "reject": RiderProfile.Status.REJECTED,
        "suspend": RiderProfile.Status.SUSPENDED,
        "reinstate": RiderProfile.Status.APPROVED,
    }
    if action not in mapping:
        messages.error(request, "Unknown rider action.")
        return _back(request, reverse("console:riders"))
    if action in {"reject", "suspend"} and not reason:
        reason = "Policy review" if action == "suspend" else "Documents incomplete"
    set_rider_status(profile, mapping[action], actor=request.user, reason=reason)
    audit(
        request,
        f"rider.{action}",
        target=profile.user.name,
        severity=AuditEvent.Severity.WARNING if action in {"reject", "suspend"} else AuditEvent.Severity.INFO,
        reason=reason,
    )
    messages.success(request, f"{profile.user.name}: {profile.get_status_display().lower()}.")
    return _back(request, reverse("console:rider_detail", args=[profile.pk]))


# --------------------------------------------------------------------------- customers
@console_required
def customers(request):
    qs = User.objects.filter(role="customer").annotate(
        order_count=Count("orders"),
        spend=Sum("orders__total", filter=Q(orders__payment_status=Order.PaymentStatus.PAID)),
    )
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(phone__icontains=query) | Q(email__icontains=query))
    if status == "suspended":
        qs = qs.filter(is_suspended=True)
    elif status == "active":
        qs = qs.filter(is_suspended=False)
    qs = qs.order_by("-order_count")
    page, querystring = _paginate(request, qs, 15)

    return render(request, "dashboard/customers.html", {
        "active_nav": "customers",
        "page_title": "Customers",
        "page_eyebrow": "People ordering fuel",
        "page": page,
        "querystring": querystring,
        "filters": {"q": query, "status": status},
        "counts": {
            "total": User.objects.filter(role="customer").count(),
            "suspended": User.objects.filter(role="customer", is_suspended=True).count(),
            "repeat": User.objects.filter(role="customer", orders__isnull=False).annotate(n=Count("orders")).filter(n__gte=2).count(),
        },
    })


@console_required
def customer_detail(request, pk):
    customer = get_object_or_404(User, pk=pk, role="customer")
    return render(request, "dashboard/customer_detail.html", {
        "active_nav": "customers",
        "page_title": customer.name,
        "page_eyebrow": "Customer profile",
        "customer": customer,
        "orders": Order.objects.select_related("station", "rider").filter(customer=customer)[:20],
        "transactions": customer.transactions.all()[:20],
        "tickets": customer.tickets.all()[:6],
        "spend": Order.objects.filter(customer=customer, payment_status=Order.PaymentStatus.PAID).aggregate(
            total=Sum("total")
        )["total"] or 0,
    })


@console_required
@require_POST
def customer_action(request, pk):
    customer = get_object_or_404(User, pk=pk, role="customer")
    action = request.POST.get("action")
    if action == "suspend":
        customer.is_suspended = True
        customer.save(update_fields=["is_suspended"])
        audit(request, "customer.suspended", target=customer.name, severity=AuditEvent.Severity.WARNING)
        messages.warning(request, f"{customer.name} suspended.")
    elif action == "activate":
        customer.is_suspended = False
        customer.save(update_fields=["is_suspended"])
        audit(request, "customer.activated", target=customer.name)
        messages.success(request, f"{customer.name} reactivated.")
    else:
        messages.error(request, "Unknown customer action.")
    return _back(request, reverse("console:customer_detail", args=[pk]))


@console_required
@require_POST
def customer_credit(request, pk):
    customer = get_object_or_404(User, pk=pk, role="customer")
    try:
        amount = int(request.POST.get("amount", "0"))
    except ValueError:
        amount = 0
    note = (request.POST.get("note") or "Goodwill credit").strip()
    if amount <= 0 or amount > 500_000:
        messages.error(request, "Enter a credit between UGX 1 and 500,000.")
        return _back(request, reverse("console:customer_detail", args=[pk]))
    credit_wallet(customer, amount, kind=Transaction.Kind.TOPUP, note=note)
    audit(request, "wallet.credit", target=customer.name, amount=amount, note=note)
    messages.success(request, f"{note}: {amount:,} UGX credited to {customer.name}.")
    return _back(request, reverse("console:customer_detail", args=[pk]))


# --------------------------------------------------------------------------- money
@console_required
def payments(request):
    qs = Transaction.objects.select_related("user", "order")
    kind = request.GET.get("kind", "")
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    if kind:
        qs = qs.filter(kind=kind)
    if status:
        qs = qs.filter(status=status)
    if query:
        qs = qs.filter(Q(reference__icontains=query) | Q(user__name__icontains=query) | Q(note__icontains=query))

    summary = qs.aggregate(net=Sum("amount"), count=Count("id"))
    inflow = qs.filter(amount__gt=0).aggregate(total=Sum("amount"))["total"] or 0
    outflow = qs.filter(amount__lt=0).aggregate(total=Sum("amount"))["total"] or 0
    page, querystring = _paginate(request, qs, 20)

    return render(request, "dashboard/payments.html", {
        "active_nav": "payments",
        "page_title": "Money",
        "page_eyebrow": "Every movement in one ledger",
        "page": page,
        "querystring": querystring,
        "kinds": Transaction.Kind.choices,
        "statuses": Transaction.Status.choices,
        "filters": {"kind": kind, "q": query, "status": status},
        "net": summary["net"] or 0,
        "count": summary["count"] or 0,
        "inflow": inflow,
        "outflow": outflow,
        "by_kind": qs.values("kind").annotate(total=Sum("amount"), n=Count("id")).order_by("-total"),
    })


@console_required
def payments_export(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="fuelondemand-ledger.csv"'
    writer = csv.writer(response)
    writer.writerow(["Reference", "When", "User", "Kind", "Method", "Amount", "Status", "Order", "Note"])
    for tx in Transaction.objects.select_related("user", "order")[:10000]:
        writer.writerow([
            tx.reference, timezone.localtime(tx.created_at).strftime("%Y-%m-%d %H:%M"),
            tx.user.name, tx.kind, tx.method, tx.amount, tx.status,
            tx.order.number if tx.order else "", tx.note,
        ])
    return response


# --------------------------------------------------------------------------- support
@console_required
def support(request):
    qs = SupportTicket.objects.select_related("customer", "order", "assignee")
    status = request.GET.get("status", "")
    priority = request.GET.get("priority", "")
    query = request.GET.get("q", "").strip()
    if status:
        qs = qs.filter(status=status)
    if priority:
        qs = qs.filter(priority=priority)
    if query:
        qs = qs.filter(Q(subject__icontains=query) | Q(customer__name__icontains=query) | Q(reference__icontains=query))
    page, querystring = _paginate(request, qs, 12)
    return render(request, "dashboard/support.html", {
        "active_nav": "support",
        "page_title": "Support",
        "page_eyebrow": "Customer conversations",
        "page": page,
        "querystring": querystring,
        "filters": {"status": status, "priority": priority, "q": query},
        "statuses": SupportTicket.Status.choices,
        "priorities": SupportTicket.Priority.choices,
        "counts": {
            "open": SupportTicket.objects.filter(status="open").count(),
            "pending": SupportTicket.objects.filter(status="pending").count(),
            "urgent": SupportTicket.objects.filter(priority="urgent").exclude(status="resolved").count(),
        },
    })


@console_required
def support_detail(request, pk):
    ticket = get_object_or_404(SupportTicket.objects.select_related("customer", "order"), pk=pk)
    return render(request, "dashboard/support_detail.html", {
        "active_nav": "support",
        "page_title": ticket.subject,
        "page_eyebrow": ticket.reference,
        "ticket": ticket,
        "statuses": SupportTicket.Status.choices,
    })


@console_required
@require_POST
def support_reply(request, pk):
    ticket = get_object_or_404(SupportTicket, pk=pk)
    reply = (request.POST.get("reply") or "").strip()
    status = request.POST.get("status") or ticket.status
    ticket.reply = reply or ticket.reply
    ticket.status = status
    ticket.assignee = request.user
    ticket.save(update_fields=["reply", "status", "assignee", "updated_at"])
    audit(request, "ticket.updated", target=ticket.reference, status=status)
    messages.success(request, f"{ticket.reference} updated.")
    return _back(request, reverse("console:support_detail", args=[pk]))


# --------------------------------------------------------------------------- settings
SETTING_FIELDS = [
    ("service_fee", "Service fee (UGX)", "int"),
    ("delivery_base", "Delivery base fee (UGX)", "int"),
    ("delivery_per_km", "Delivery fee per km (UGX)", "int"),
    ("support_phone", "Support phone line", "text"),
    ("announcement", "Console banner announcement", "text"),
    ("payout_schedule", "Rider payout schedule", "text"),
]


@console_required
def settings_view(request):
    if request.method == "POST":
        changed = {}
        for key, _label, kind in SETTING_FIELDS:
            if key not in request.POST:
                continue
            value = request.POST.get(key, "").strip()
            if kind == "int":
                try:
                    value = str(max(0, int(value or 0)))
                except ValueError:
                    messages.error(request, "Fees must be whole numbers.")
                    continue
            if value != get_setting(key, ""):
                set_setting(key, value, actor=request.user)
                changed[key] = value
        if changed:
            audit(request, "settings.updated", target=", ".join(changed.keys()), values=changed)
            messages.success(request, "Operations settings saved.")
        else:
            messages.info(request, "Nothing changed.")
        return redirect("console:settings")

    return render(request, "dashboard/settings.html", {
        "active_nav": "settings",
        "page_title": "Settings",
        "page_eyebrow": "Business rules the apps read",
        "rows": [
            {"key": key, "label": label, "kind": kind, "value": get_setting(key, str(getattr_settings_default(key)))}
            for key, label, kind in SETTING_FIELDS
        ],
        "security": _security_summary(),
    })


def getattr_settings_default(key: str):
    from django.conf import settings as dj_settings

    return {
        "service_fee": dj_settings.FC["service_fee"],
        "delivery_base": dj_settings.FC["delivery_base"],
        "delivery_per_km": dj_settings.FC["delivery_per_km"],
        "support_phone": dj_settings.FC["support_phone"],
        "payout_schedule": "Weekly, every Friday",
    }.get(key, "")


def _security_summary() -> list[dict]:
    return [
        {"label": "Session idle timeout", "value": f"{settings.SESSION_COOKIE_AGE // 60} minutes"},
        {"label": "Failed login lockout", "value": f"{settings.CONSOLE_MAX_FAILURES} attempts / {settings.CONSOLE_LOCKOUT_SECONDS // 60} min"},
        {"label": "Console access", "value": "Staff with console rights only"},
        {"label": "CSRF protection", "value": "Enabled on every form"},
        {"label": "HTTPS enforcement", "value": "On when DEBUG=false"},
        {"label": "Audit logging", "value": "All mutations recorded"},
    ]


# --------------------------------------------------------------------------- audit
@console_required
def audit_log(request):
    qs = AuditEvent.objects.select_related("actor")
    severity = request.GET.get("severity", "")
    query = request.GET.get("q", "").strip()
    if severity:
        qs = qs.filter(severity=severity)
    if query:
        qs = qs.filter(Q(action__icontains=query) | Q(target__icontains=query) | Q(actor__name__icontains=query))
    page, querystring = _paginate(request, qs, 25)
    return render(request, "dashboard/audit.html", {
        "active_nav": "audit",
        "page_title": "Security log",
        "page_eyebrow": "Every privileged action",
        "page": page,
        "querystring": querystring,
        "filters": {"severity": severity, "q": query},
        "severities": AuditEvent.Severity.choices,
        "counts": {
            "critical": AuditEvent.objects.filter(severity="critical").count(),
            "warning": AuditEvent.objects.filter(severity="warning").count(),
            "total": AuditEvent.objects.count(),
        },
    })
