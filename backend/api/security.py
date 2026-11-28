"""Auth primitives for /api/v1: JSON helpers, JWT, throttling, guards.

The Flutter `ApiClient` expects `{message}` / `{errors}` envelopes, so every
failure here is shaped that way.
"""
from __future__ import annotations

import functools
import json
from datetime import datetime, timedelta, timezone as dt_timezone

import jwt
from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from core.models import User
from core.services import DomainError
from core.utils import client_ip


class TooMany(Exception):
    pass


# --------------------------------------------------------------------------- JSON
def ok(data: dict | list | None = None, status: int = 200, **extra) -> JsonResponse:
    payload = {"ok": True}
    if isinstance(data, dict):
        payload.update(data)
    elif data is not None:
        payload["data"] = data
    payload.update(extra)
    return JsonResponse(payload, status=status)


def fail(message: str, status: int = 400, errors: dict | None = None) -> JsonResponse:
    payload = {"ok": False, "message": message}
    if errors:
        payload["errors"] = errors
    return JsonResponse(payload, status=status)


def read_json(request) -> dict:
    if not request.body:
        return {}
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def require_method(request, *methods):
    return request.method.upper() in {m.upper() for m in methods}


def endpoint(view):
    """Token-authenticated JSON endpoint: CSRF exempt, errors as `{message}`."""

    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except DomainError as exc:
            return fail(str(exc), 409)
        except TooMany:
            return fail("Too many attempts. Please wait a moment and try again.", 429)
        except User.DoesNotExist:
            return fail("We could not find that account.", 404)

    return csrf_exempt(wrapper)


# --------------------------------------------------------------------------- JWT
def issue_token(user: User, ttl: int | None = None) -> str:
    now = datetime.now(tz=dt_timezone.utc)
    payload = {
        "sub": str(user.pk),
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl or settings.JWT_ACCESS_TTL)).timestamp()),
        "jti": f"{user.pk}-{int(now.timestamp())}",
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"], options={"require": ["exp", "sub"]})
    except jwt.PyJWTError:
        return None


def bearer(request) -> str:
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return ""


def current_user(request) -> User | None:
    token = bearer(request)
    payload = decode_token(token) if token else None
    if not payload:
        return None
    user = User.objects.select_related("rider").filter(pk=payload.get("sub")).first()
    if not user or not user.is_active or user.is_suspended:
        return None
    return user


def require_auth(*roles: str):
    """Decorator: valid bearer token, active account, optional role gate."""

    def decorator(view):
        @functools.wraps(view)
        def wrapper(request, *args, **kwargs):
            if not bearer(request):
                return fail("Please sign in to continue.", 401)
            user = current_user(request)
            if not user:
                return fail("Your session has expired. Please sign in again.", 401)
            if roles and user.role not in roles:
                return fail("This action is not available for your account type.", 403)
            request.api_user = user
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


# --------------------------------------------------------------------------- throttle
def throttle(scope: str, identity: str, limit: int, window_seconds: int) -> None:
    key = f"throttle:{scope}:{identity}"
    hits = cache.get(key, 0) + 1
    if hits > limit:
        raise TooMany
    cache.set(key, hits, window_seconds)


def throttle_ip(request, scope: str, limit: int, window_seconds: int) -> None:
    throttle(scope, client_ip(request) or "unknown", limit, window_seconds)
