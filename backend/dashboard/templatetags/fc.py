"""Template filters for the console."""
from __future__ import annotations

from datetime import datetime

from django import template
from django.utils import timezone
from django.utils.safestring import mark_safe

from core.utils import compact_ugx, percent, ugx

register = template.Library()


@register.filter
def money(value) -> str:
    return ugx(value)


@register.filter
def short(value) -> str:
    return compact_ugx(value)


@register.filter
def pct(part, whole) -> float:
    return percent(part, whole)


@register.filter
def pct_signed(value) -> str:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "0%"
    text = f"{value:+.1f}"
    if text.endswith(".0"):
        text = text[:-2]
    return f"{text}%"


@register.filter
def initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p][:2]
    return "".join(p[0] for p in parts).upper() or "FC"


def _plural(count: int, singular: str) -> str:
    return f"{count} {singular}{'' if count == 1 else 's'}"


def _as_datetime(value):
    """Accept datetimes, ISO strings (analytics payloads) or nothing."""
    if not value:
        return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            value = datetime.fromisoformat(raw)
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return value


@register.filter
def ago(value) -> str:
    moment = _as_datetime(value)
    if moment is None:
        return "—"
    seconds = int((timezone.now() - moment).total_seconds())
    if seconds < 0:
        return "just now"
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return _plural(seconds // 60, "min") + " ago"
    if seconds < 86400:
        return _plural(seconds // 3600, "hour") + " ago"
    return _plural(seconds // 86400, "day") + " ago"


@register.filter
def clock(value) -> str:
    moment = _as_datetime(value)
    if moment is None:
        return "—"
    return timezone.localtime(moment).strftime("%H:%M")


@register.filter
def daystamp(value) -> str:
    moment = _as_datetime(value)
    if moment is None:
        return "—"
    return timezone.localtime(moment).strftime("%d %b · %H:%M")


@register.filter
def status_tone(status: str) -> str:
    return {
        "delivered": "ok",
        "cancelled": "bad",
        "pending_payment": "muted",
        "confirmed": "gold",
        "assigned": "info",
        "picked_up": "violet",
        "arrived": "teal",
        "open": "gold",
        "pending": "info",
        "loaded": "violet",
        "in_transit": "gold",
        "offloaded": "ok",
        "completed": "ok",
        "active": "ok",
        "idle": "muted",
        "maintenance": "gold",
        "reconciled": "ok",
        "resolved": "ok",
        "approved": "ok",
        "rejected": "bad",
        "suspended": "bad",
        "paid": "ok",
        "unpaid": "muted",
        "refunded": "violet",
        "failed": "bad",
        "successful": "ok",
        "online": "ok",
        "offline": "muted",
        "critical": "bad",
        "warning": "gold",
        "info": "info",
        "urgent": "bad",
        "order": "info",
        "promo": "violet",
        "system": "muted",
        "wallet": "gold",
    }.get(status, "muted")


@register.filter
def brand_tone(brand: str) -> str:
    return {"stabex": "gold", "shell": "bad", "total": "info", "hashi": "violet"}.get(brand, "muted")


@register.filter
def price_for(station, fuel_type):
    """`{{ station|price_for:"petrol" }}` → UGX per litre, or blank."""
    try:
        return station.price_for(fuel_type) or ""
    except Exception:
        return ""


@register.filter
def signed(value) -> str:
    amount = int(value or 0)
    return f"+{amount:,}" if amount > 0 else f"{amount:,}"

# --------------------------------------------------------------------------- icons
# Stroke icons drawn as raw paths so the console ships zero icon dependencies.
ICONS = {
    "overview": '<rect x="3" y="3" width="7" height="9" rx="1.6"/><rect x="14" y="3" width="7" height="5" rx="1.6"/><rect x="14" y="12" width="7" height="9" rx="1.6"/><rect x="3" y="16" width="7" height="5" rx="1.6"/>',
    "live": '<circle cx="12" cy="12" r="2.4"/><path d="M7.8 7.8a6 6 0 0 0 0 8.4M16.2 16.2a6 6 0 0 0 0-8.4"/><path d="M4.9 4.9a10 10 0 0 0 0 14.2M19.1 19.1a10 10 0 0 0 0-14.2"/>',
    "orders": '<path d="M5 3h14v18l-2.5-1.6L14 21l-2-1.6L10 21l-2.5-1.6L5 21z"/><path d="M9 8h6M9 12h6"/>',
    "stations": '<path d="M4 21V5a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v16"/><path d="M4 11h10"/><path d="M14 8h3l3 3v7a1.6 1.6 0 0 1-3.2 0v-5H14"/><path d="M2 21h14"/>',
    "riders": '<circle cx="5.5" cy="17.5" r="3"/><circle cx="18.5" cy="17.5" r="3"/><path d="M5.5 17.5 9 9h5l3 8.5"/><path d="M9 9 7.5 5H5"/><circle cx="15" cy="5" r="1.6"/>',
    "customers": '<circle cx="9" cy="8" r="3.2"/><path d="M2.8 20a6.2 6.2 0 0 1 12.4 0"/><path d="M17 5.2a3 3 0 0 1 0 5.6"/><path d="M18 14.4a5.4 5.4 0 0 1 3.2 4.9"/>',
    "payments": '<path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H19v3"/><rect x="3" y="7.5" width="18" height="12" rx="2.4"/><path d="M16 13.5h2.5"/>',
    "support": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3.6"/><path d="m5.6 5.6 3.9 3.9M14.5 14.5l3.9 3.9M18.4 5.6l-3.9 3.9M9.5 14.5l-3.9 3.9"/>',
    "settings": '<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h9M17 18h3"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="15" cy="18" r="2"/>',
    "audit": '<path d="M12 3 5 6v6c0 4.2 2.9 7.7 7 9 4.1-1.3 7-4.8 7-9V6z"/><path d="m9.2 12.2 2 2 3.6-3.9"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/>',
    "bell": '<path d="M18 15.5V10a6 6 0 1 0-12 0v5.5L4.5 18h15z"/><path d="M10 21h4"/>',
    "logout": '<path d="M14 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4"/><path d="m9 8-4 4 4 4"/><path d="M5 12h10"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "download": '<path d="M12 3v12"/><path d="m7.5 10.5 4.5 4.5 4.5-4.5"/><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>',
    "arrow": '<path d="M19 12H5"/><path d="m11 6-6 6 6 6"/>',
    "check": '<path d="m5 12.5 4.5 4.5L19 7"/>',
    "close": '<path d="M6 6l12 12M18 6 6 18"/>',
    "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
    "filter": '<path d="M4 5h16l-6.4 7.6V20l-3.2-1.8v-5.6z"/>',
    "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "trend-up": '<path d="m4 16 5.5-5.5 3.5 3.5L20 8"/><path d="M15 8h5v5"/>',
    "trend-down": '<path d="m4 8 5.5 5.5 3.5-3.5L20 16"/><path d="M15 16h5v-5"/>',
    "alert": '<path d="M12 4 3 20h18z"/><path d="M12 10v4.5M12 17.4v.1"/>',
    "phone": '<path d="M6 3.5h3l1.5 4-2 1.5a11 11 0 0 0 6.5 6.5l1.5-2 4 1.5v3a2 2 0 0 1-2.2 2A16.5 16.5 0 0 1 4 5.7 2 2 0 0 1 6 3.5z"/>',
    "map": '<path d="m9 4 6 2 5-2v14l-5 2-6-2-5 2V6z"/><path d="M9 4v14M15 6v14"/>',
    "refresh": '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>',
    "external": '<path d="M14 4h6v6"/><path d="M20 4 11 13"/><path d="M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4"/>',
    "eye": '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "eye-off": '<path d="M10 5.2A10.6 10.6 0 0 1 12 5c6.4 0 10 7 10 7a13 13 0 0 1-2.1 3.1"/><path d="M6.3 6.4A13.4 13.4 0 0 0 2 12s3.6 7 10 7a9.6 9.6 0 0 0 4.4-1.1"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/><path d="m3 3 18 18"/>',
    "fuel": '<path d="M5 21V5a2 2 0 0 1 2-2h5a2 2 0 0 1 2 2v16"/><path d="M5 10h9"/><path d="M14 8h2.5l3 3v6.5a1.8 1.8 0 0 1-3.6 0V13H14"/><path d="M3 21h14"/>',
    "pin": '<path d="M12 21s7-6.1 7-11a7 7 0 1 0-14 0c0 4.9 7 11 7 11z"/><circle cx="12" cy="10" r="2.6"/>',
    "wallet": '<path d="M3 8a2.5 2.5 0 0 1 2.5-2.5H19V8"/><rect x="3" y="8" width="18" height="11" rx="2.4"/><path d="M16 13.5h2.5"/>',
    "star": '<path d="m12 3.8 2.6 5.3 5.9.9-4.3 4.1 1 5.9-5.2-2.8-5.2 2.8 1-5.9L3.5 10l5.9-.9z"/>',
    "bike": '<circle cx="5.5" cy="17.5" r="3"/><circle cx="18.5" cy="17.5" r="3"/><path d="M5.5 17.5 9 9h5l3 8.5"/><path d="M9 9 7.5 5H5"/>',
    "user": '<circle cx="12" cy="8" r="3.4"/><path d="M5 20a7 7 0 0 1 14 0"/>',
    "grid": '<rect x="3" y="3" width="8" height="8" rx="1.6"/><rect x="13" y="3" width="8" height="8" rx="1.6"/><rect x="3" y="13" width="8" height="8" rx="1.6"/><rect x="13" y="13" width="8" height="8" rx="1.6"/>',
    "ticket": '<path d="M4 8a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-2a2 2 0 0 0 0-4z"/><path d="M12 6v12"/>',
    "shield": '<path d="M12 3 5 6v6c0 4.2 2.9 7.7 7 9 4.1-1.3 7-4.8 7-9V6z"/>',
    "bolt": '<path d="M13 3 5 14h6l-1 7 8-11h-6z"/>',
    "trash": '<path d="M4 7h16"/><path d="M9 7V5h6v2"/><path d="M6 7l1 13h10l1-13"/><path d="M10 11v6M14 11v6"/>',
    "report": '<path d="M5 3h9l5 5v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/><path d="M14 3v5h5"/><path d="M8 17v-4M12 17v-6M16 17v-2"/>',
    "spark": '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18"/>',
    "expand": '<path d="M9 4H5.5A1.5 1.5 0 0 0 4 5.5V9"/><path d="M15 4h3.5A1.5 1.5 0 0 1 20 5.5V9"/><path d="M9 20H5.5A1.5 1.5 0 0 1 4 18.5V15"/><path d="M15 20h3.5a1.5 1.5 0 0 0 1.5-1.5V15"/>',
    "minus": '<path d="M5 12h14"/>',
    "locate": '<circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="7.5"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2"/>',
    "chevron": '<path d="m6 9.5 6 6 6-6"/>',
    "route": '<circle cx="6" cy="5" r="2.2"/><circle cx="18" cy="19" r="2.2"/><path d="M6 7.2V14a3 3 0 0 0 3 3h6.3"/>',
}


@register.simple_tag
def icon(name: str, size=18, stroke="1.7", cls=""):
    body = ICONS.get(name, ICONS["grid"])
    return mark_safe(
        f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="none" stroke="currentColor" '
        f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round" class="{cls}" '
        f'aria-hidden="true">{body}</svg>'
    )


@register.simple_tag
def delta_class(value) -> str:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "flat"
    return "up" if value > 0 else "down" if value < 0 else "flat"


register.filter("delta_class", delta_class)


@register.filter
def first_letter(name: str) -> str:
    return (name or "F")[0].upper()


@register.filter
def tone_class(status) -> str:
    """Icon tone for a status, used by the dashboard operation lists."""
    return {
        "delivered": "tone-green",
        "cancelled": "tone-rose",
        "confirmed": "tone-gold",
        "pending_payment": "tone-sky",
        "assigned": "tone-blue",
        "picked_up": "tone-violet",
        "arrived": "tone-teal",
    }.get(status, "tone-gold")
