"""Small, dependency-free helpers shared by the API and the console."""
from __future__ import annotations

import math
import secrets
import string
from datetime import timedelta

from django.utils import timezone

UGX = "UGX"


def normalize_phone(raw: str) -> str:
    """`0700 123456`, `256700123456`, `+256700123456` → `+256700123456`."""
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    if not digits:
        return ""
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0"):
        digits = "256" + digits[1:]
    if not digits.startswith("256") and len(digits) <= 9:
        digits = "256" + digits
    return f"+{digits}"


def ugx(amount: int | float | None) -> str:
    """1_234_500 → `UGX 1,234,500`."""
    value = int(round(amount or 0))
    return f"{UGX} {value:,}"


def compact_ugx(amount: int | float | None) -> str:
    """1_234_500 → `1.23M` (used on dense dashboard cards)."""
    value = float(amount or 0)
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.2f}M".replace(".00M", "M")
    if abs(value) >= 1_000:
        return f"{value / 1_000:.1f}K".replace(".0K", "K")
    return f"{value:,.0f}"


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return round(2 * radius * math.asin(math.sqrt(a)), 2)


def reference(prefix: str, length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return prefix + "".join(secrets.choice(alphabet) for _ in range(length))


def numeric_code(digits: int = 6) -> str:
    return "".join(secrets.choice(string.digits) for _ in range(digits))


def order_number(sequence: int, day=None) -> str:
    stamp = (day or timezone.localdate()).strftime("%y%m%d")
    return f"FOD-{stamp}-{sequence:04d}"


def client_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def percent(part: float, whole: float) -> float:
    return round((part / whole) * 100, 1) if whole else 0.0


def day_range(days: int = 14):
    """`days` consecutive local dates ending today (oldest first)."""
    today = timezone.localdate()
    return [today - timedelta(days=offset) for offset in range(days - 1, -1, -1)]
