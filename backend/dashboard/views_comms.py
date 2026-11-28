"""Notifications: the console outbox used to reach customers, riders, tanker drivers and stations."""
from __future__ import annotations

from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import Notification, Role, User
from core.services import DomainError, broadcast_notification

from .decorators import console_required

AUDIENCES = [
    ("customers", "All customers"),
    ("riders", "All riders"),
    ("tankers", "Tanker drivers"),
    ("stations", "Station staff"),
    ("everyone", "Everyone"),
]


@console_required
def notifications(request):
    kind = request.GET.get("kind", "")
    role = request.GET.get("role", "")
    term = (request.GET.get("q") or "").strip()

    base = Notification.objects.all()
    rows = base.select_related("user")
    if kind:
        rows = rows.filter(kind=kind)
    if role:
        rows = rows.filter(user__role=role)
    if term:
        rows = rows.filter(
            Q(title__icontains=term) | Q(body__icontains=term) | Q(user__name__icontains=term)
        )

    today = timezone.localdate()
    stats = {
        "sent": base.count(),
        "today": base.filter(created_at__date=today).count(),
        "unread": base.filter(read_at__isnull=True).count(),
        "reach": base.values("user").distinct().count(),
    }
    kind_counts = {
        row["kind"]: row["count"] for row in base.values("kind").annotate(count=Count("id"))
    }

    return render(request, "dashboard/notifications.html", {
        "active_nav": "notifications",
        "page_title": "Notifications",
        "page_eyebrow": f"{stats['sent']:,} messages pushed to the network",
        "rows": rows[:120],
        "stats": stats,
        "kind_counts": kind_counts,
        "kinds": Notification.Kind.choices,
        "roles": Role.choices,
        "audiences": AUDIENCES,
        "filters": {"kind": kind, "role": role, "q": term},
    })


@console_required
@require_POST
def notification_broadcast(request):
    try:
        sent = broadcast_notification(
            audience=request.POST.get("audience", ""),
            kind=request.POST.get("kind", ""),
            title=request.POST.get("title", ""),
            body=request.POST.get("body", ""),
            actor=request.user,
        )
    except DomainError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Message delivered to {sent:,} recipient{'s' if sent != 1 else ''}.")
    return redirect("console:notifications")


@console_required
@require_POST
def notification_delete(request, pk):
    row = get_object_or_404(Notification, pk=pk)
    label = row.title
    row.delete()
    messages.success(request, f"Deleted notification “{label[:60]}”.")
    return redirect("console:notifications")