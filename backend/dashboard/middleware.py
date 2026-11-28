"""Console access control, response hardening and idle-session tracking."""
from __future__ import annotations

from urllib.parse import quote

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

User = get_user_model()

LOGIN_PATH = "/console/login/"


class ConsoleSecurityMiddleware:
    """Defence in depth around /console:

    * anonymous visitors are bounced to the branded login with `?next=`
    * authenticated users without console rights get a hard 403
    * every console response is non-cacheable and non-indexable
    * an idle operator's `last_seen_at` is refreshed at most once a minute
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/console/"):
            if not request.path.startswith(LOGIN_PATH):
                user = getattr(request, "user", None)
                if not user or not user.is_authenticated:
                    return redirect(f"{reverse('console:login')}?next={quote(request.get_full_path())}")
                if not user.can_use_console:
                    return HttpResponseForbidden(
                        "<h1 style='font-family:system-ui;color:#F5C72E;background:#080A0C;padding:40px'>"
                        "This account does not have console access.</h1>"
                    )
                key = f"console-seen:{user.pk}"
                if not cache.get(key):
                    cache.set(key, 1, 60)
                    User.objects.filter(pk=user.pk).update(last_seen_at=timezone.now())

            response = self.get_response(request)
            response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response["Pragma"] = "no-cache"
            response["X-Robots-Tag"] = "noindex, nofollow"
            response["Permissions-Policy"] = "geolocation=(self), camera=(), microphone=()"
            return response

        return self.get_response(request)
