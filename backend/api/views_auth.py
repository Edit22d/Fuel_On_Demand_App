"""Auth endpoints: register, login, OTP, password reset, profile."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone
import logging
import re

import jwt
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone
from google.auth import exceptions as google_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from core.models import AuditEvent, OtpCode, Role, User
from core.services import audit, issue_otp, notify, send_otp_notification, verify_otp
from core.utils import client_ip, normalize_phone
from .security import endpoint, fail, issue_token, ok, read_json, require_auth, require_method, throttle
from .serializers import user_payload

FC = settings.FC
logger = logging.getLogger("fuelondemand.security")


def _reset_token(user: User) -> str:
    now = datetime.now(tz=dt_timezone.utc)
    return jwt.encode(
        {"sub": str(user.pk), "purpose": "reset", "exp": int((now + timedelta(minutes=15)).timestamp())},
        settings.JWT_SECRET,
        algorithm="HS256",
    )


def _otp_response(phone: str, purpose: str, code: str, delivery: dict) -> dict:
    payload = {
        "otp_required": True,
        "phone": phone,
        "purpose": purpose,
        "expires_in": FC["otp_ttl_seconds"],
        "resend_in": FC["otp_resend_seconds"],
        "confirmation_sent": delivery["sent"],
        "delivery": delivery,
    }
    if delivery.get("destination"):
        payload["destination"] = delivery["destination"]
    if FC["otp_show_code"]:  # demo switch — never enable in production
        payload["dev_code"] = code
    return payload


def _issue_and_deliver(user: User, purpose: str, *, respect_cooldown: bool = True) -> dict:
    otp, code = issue_otp(user.phone, purpose, respect_cooldown=respect_cooldown)
    try:
        delivery = send_otp_notification(user, code, purpose)
    except Exception:
        logger.exception("Could not send OTP for %s (%s)", user.phone, purpose)
        delivery = {
            "channel": "email" if user.email else None,
            "destination": user.email or None,
            "sent": False,
        }
    return _otp_response(user.phone, purpose, code, delivery)


def _verify_google_id_token(raw_token: str) -> dict | None:
    if not settings.GOOGLE_OAUTH_CLIENT_IDS:
        return None
    try:
        unverified = jwt.decode(raw_token, options={"verify_signature": False})
        audience = unverified.get("aud")
        if audience not in settings.GOOGLE_OAUTH_CLIENT_IDS:
            return None
        claims = google_id_token.verify_oauth2_token(
            raw_token,
            google_requests.Request(),
            audience=audience,
            clock_skew_in_seconds=30,
        )
    except (jwt.PyJWTError, ValueError, KeyError, google_exceptions.GoogleAuthError):
        return None
    return claims if claims.get("email_verified") is True else None


@endpoint
def google_login(request):
    if not require_method(request, "POST"):
        return fail("Method not allowed.", 405)
    data = read_json(request)
    raw_token = str(data.get("id_token") or "").strip()
    if not raw_token:
        return fail("A Google sign-in token is required.", 422)
    if not settings.GOOGLE_OAUTH_CLIENT_IDS:
        return fail("Google sign-in is not configured on the server.", 503)

    throttle("google", client_ip(request) or "anonymous", 10, 900)
    claims = _verify_google_id_token(raw_token)
    if not claims:
        return fail("Google sign-in could not be verified. Please try again.", 401)

    google_sub = str(claims.get("sub") or "").strip()
    email = str(claims.get("email") or "").strip().lower()
    name = str(claims.get("name") or email.partition("@")[0] or "Google User").strip()[:120]
    if not google_sub or not email or len(name) < 2:
        return fail("Google did not return the account details needed to sign in.", 422)

    user = User.objects.filter(google_sub=google_sub).first()
    if user is None:
        user = User.objects.filter(email__iexact=email).first()
        if user is not None:
            if user.google_sub and user.google_sub != google_sub:
                return fail("This email is linked to a different Google account.", 409)
            changed = []
            if not user.google_sub:
                user.google_sub = google_sub
                changed.append("google_sub")
            if not user.is_verified:
                user.is_verified = True
                changed.append("is_verified")
            if changed:
                user.save(update_fields=changed)
            audit(None, "api.google_linked", target=user.phone, actor=user)
        else:
            raw_phone = data.get("phone")
            if not raw_phone:
                return ok({"phone_required": True, "email": email, "name": name})
            phone = normalize_phone(str(raw_phone))
            if len(phone) < 12:
                return fail("Enter a valid Ugandan phone number.", 422, {"phone": ["Enter a valid Ugandan phone number."]})
            if User.objects.filter(phone=phone).exists():
                return fail("An account with this number already exists. Try signing in.", 422, {"phone": ["Already registered."]})
            try:
                with transaction.atomic():
                    user = User.objects.create_user(
                        phone=phone,
                        password=None,
                        name=name,
                        email=email,
                        google_sub=google_sub,
                        is_verified=True,
                    )
                    audit(None, "customer.google_registered", target=phone, actor=user)
                    notify(user, "Welcome to FuelOnDemand", "Your account was created securely with Google.")
            except IntegrityError:
                return fail("An account with these details already exists. Try signing in.", 422)

    if user.is_suspended or not user.is_active:
        return fail("This account has been suspended. Contact support on " + FC["support_phone"], 403)
    if user.role == Role.RIDER and getattr(user, "rider", None) and user.rider.status != "approved":
        return fail(f"Your rider application is {user.rider.get_status_display().lower()}.", 403)

    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])
    audit(None, "api.google_login", target=user.phone, actor=user)
    return ok({"token": issue_token(user), "user": user_payload(user)})


@endpoint
def register(request):
    if not require_method(request, "POST"):
        return fail("Method not allowed.", 405)
    data = read_json(request)
    phone = normalize_phone(data.get("phone", ""))
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""

    errors = {}
    if len(name) < 2:
        errors["name"] = ["Enter your full name."]
    if len(phone) < 12:
        errors["phone"] = ["Enter a valid Ugandan phone number."]
    try:
        validate_email(email)
    except ValidationError:
        errors["email"] = ["Enter a valid email address."]
    if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        errors["password"] = ["Use at least 8 characters with a letter and a number."]
    if errors:
        return fail("Please check the details you entered.", 422, errors)
    if User.objects.filter(phone=phone).exists():
        return fail("An account with this number already exists. Try signing in.", 422, {"phone": ["Already registered."]})
    if User.objects.filter(email__iexact=email).exists():
        return fail("An account with this email already exists. Try signing in.", 422, {"email": ["Already registered."]})

    throttle("register", client_ip(request) or phone, 5, 3600)
    try:
        with transaction.atomic():
            user = User.objects.create_user(
                phone=phone, password=password, name=name, email=email, is_verified=False
            )
            audit(None, "customer.registered", target=phone, actor=user)
            notify(user, "Welcome to FuelOnDemand", "Your account has been created. Confirm it with the code we sent by email.")
    except IntegrityError:
        return fail("An account with these details already exists. Try signing in.", 422)
    return ok(_issue_and_deliver(user, OtpCode.Purpose.SIGNUP), status=201)


@endpoint
def login(request):
    if not require_method(request, "POST"):
        return fail("Method not allowed.", 405)
    data = read_json(request)
    phone = normalize_phone(data.get("phone", ""))
    password = data.get("password") or ""

    throttle("login", f"{client_ip(request)}:{phone}", 10, 900)
    user = User.objects.filter(phone=phone).first()
    if not user or not user.check_password(password):
        audit(None, "api.login_failed", target=phone, severity=AuditEvent.Severity.WARNING)
        return fail("That phone number or password is not correct.", 401)

    if user.is_suspended or not user.is_active:
        return fail("This account has been suspended. Contact support on " + FC["support_phone"], 403)
    if user.role == Role.RIDER and getattr(user, "rider", None) and user.rider.status != "approved":
        return fail(f"Your rider application is {user.rider.get_status_display().lower()}.", 403)
    if not user.is_verified:
        audit(None, "api.verification_required", target=phone, actor=user)
        return ok(_issue_and_deliver(user, OtpCode.Purpose.SIGNUP, respect_cooldown=False))

    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])
    audit(None, "api.login", target=phone, actor=user)

    if FC["otp_on_login"]:
        return ok(_issue_and_deliver(user, OtpCode.Purpose.LOGIN))

    return ok({"token": issue_token(user), "user": user_payload(user)})


@endpoint
def otp_send(request):
    if not require_method(request, "POST"):
        return fail("Method not allowed.", 405)
    data = read_json(request)
    phone = normalize_phone(data.get("phone", ""))
    purpose = data.get("purpose", "login")
    if purpose not in dict(OtpCode.Purpose.choices):
        return fail("Unknown verification purpose.", 422)
    user = User.objects.filter(phone=phone).first()
    if not user:
        return fail("We could not find that account.", 404)
    if user.is_suspended or not user.is_active:
        return fail("This account has been suspended. Contact support.", 403)
    if purpose != OtpCode.Purpose.SIGNUP and not user.is_verified:
        return fail("Confirm your account before requesting this code.", 403)

    throttle("otp", f"{client_ip(request)}:{phone}", 6, 600)
    return ok(_issue_and_deliver(user, purpose))


@endpoint
def otp_verify(request):
    if not require_method(request, "POST"):
        return fail("Method not allowed.", 405)
    data = read_json(request)
    phone = normalize_phone(data.get("phone", ""))
    purpose = data.get("purpose", "login")
    code = str(data.get("code", "")).strip()

    throttle("otp-verify", f"{client_ip(request)}:{phone}", 12, 600)
    if not verify_otp(phone, purpose, code):
        return fail("That code is incorrect or has expired.", 422, {"code": ["Incorrect or expired."]})

    user = User.objects.filter(phone=phone).first()
    if not user:
        return fail("We could not find that account.", 404)
    if user.is_suspended or not user.is_active:
        return fail("This account has been suspended. Contact support.", 403)
    if purpose == OtpCode.Purpose.RESET:
        return ok({"reset_token": _reset_token(user)})
    if purpose != OtpCode.Purpose.SIGNUP and not user.is_verified:
        return fail("Confirm your account with the sign-up code first.", 403)

    if purpose == OtpCode.Purpose.SIGNUP and not user.is_verified:
        user.is_verified = True
        user.save(update_fields=["is_verified"])
        notify(user, "Account confirmed", "Your FuelOnDemand account is verified and ready to use.")
        audit(None, "api.account_verified", target=phone, actor=user)
    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])
    audit(None, "api.otp_verified", target=phone, actor=user)
    return ok({"token": issue_token(user), "user": user_payload(user)})


@endpoint
def forgot(request):
    if not require_method(request, "POST"):
        return fail("Method not allowed.", 405)
    phone = normalize_phone(read_json(request).get("phone", ""))
    throttle("forgot", f"{client_ip(request)}:{phone}", 5, 3600)
    user = User.objects.filter(phone=phone).first()
    if not user or user.is_suspended or not user.is_active:
        # Do not leak which numbers are registered.
        return ok({"otp_required": True, "phone": phone, "purpose": "reset", "expires_in": FC["otp_ttl_seconds"]})
    return ok(_issue_and_deliver(user, OtpCode.Purpose.RESET))


@endpoint
def reset(request):
    if not require_method(request, "POST"):
        return fail("Method not allowed.", 405)
    data = read_json(request)
    phone = normalize_phone(data.get("phone", ""))
    token = data.get("reset_token", "")
    password = data.get("password", "")
    confirm = data.get("password_confirmation", password)

    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        if payload.get("purpose") != "reset":
            raise jwt.InvalidTokenError
        user = User.objects.get(pk=payload["sub"], phone=phone)
    except (jwt.PyJWTError, User.DoesNotExist, KeyError):
        return fail("This reset link has expired. Request a new code.", 401)

    if password != confirm:
        return fail("Passwords do not match.", 422, {"password_confirmation": ["Passwords do not match."]})
    if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return fail("Use at least 8 characters with a letter and a number.", 422, {"password": ["Too weak."]})

    user.set_password(password)
    user.save(update_fields=["password"])
    audit(None, "api.password_reset", target=phone, actor=user)
    notify(user, "Password changed", "Your FuelOnDemand password was just changed.", "system")
    return ok({"message": "Password updated. You can sign in now."})


@endpoint
@require_auth()
def logout(request):
    if not require_method(request, "POST"):
        return fail("Method not allowed.", 405)
    user = getattr(request, "api_user", None)
    return ok({"message": "Signed out."})


@endpoint
@require_auth()
def me(request):
    user = request.api_user
    if require_method(request, "POST"):
        return fail("Method not allowed.", 405)
    if require_method(request, "PUT", "PATCH"):
        data = read_json(request)
        changed = []
        for field, limit in (("name", 120), ("email", 254), ("emergency_contact", 32)):
            if field in data:
                setattr(user, field, str(data[field])[:limit])
                changed.append(field)
        if "name" in changed and len(user.name.strip()) < 2:
            return fail("Enter your full name.", 422, {"name": ["Enter your full name."]})
        if "email" in changed:
            user.email = user.email.strip()
            try:
                validate_email(user.email)
            except ValidationError:
                return fail("Enter a valid email address.", 422, {"email": ["Enter a valid email address."]})
            if User.objects.filter(email__iexact=user.email).exclude(pk=user.pk).exists():
                return fail("That email is already registered.", 422, {"email": ["Already registered."]})
        if changed:
            user.save(update_fields=changed)
    return ok({"user": user_payload(user)})
