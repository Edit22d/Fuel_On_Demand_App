"""Template context available to every console page."""
from __future__ import annotations

from django.conf import settings
from django.core.cache import cache

from core.models import Notification, RiderProfile, SupportTicket, Tanker


def console(request):
    if not request.path.startswith("/console/"):
        return {}

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"FC": settings.FC}

    counts = cache.get("console-alert-counts")
    if counts is None:
        counts = {
            "riders": RiderProfile.objects.filter(status=RiderProfile.Status.PENDING).count(),
            "tickets": SupportTicket.objects.filter(status=SupportTicket.Status.OPEN).count(),
            "tankers": Tanker.objects.filter(is_verified=False).count(),
            "notifications": Notification.objects.filter(read_at__isnull=True).count(),
        }
        cache.set("console-alert-counts", counts, 30)

    return {
        "FC": settings.FC,
        "console_user": user,
        "alert_riders": counts.get("riders", 0),
        "alert_tickets": counts.get("tickets", 0),
        "alert_tankers": counts.get("tankers", 0),
        "alert_notifications": counts.get("notifications", 0),
        "refresh_ms": settings.FC["console_refresh_ms"],
    }
