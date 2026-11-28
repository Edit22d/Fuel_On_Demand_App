"""Shared console guards."""
from __future__ import annotations

import functools
from urllib.parse import quote

from django.shortcuts import redirect, render
from django.urls import reverse


def console_required(view):
    """Authenticated + console-enabled. Views are the source of truth; the
    middleware does the same check earlier for a cleaner redirect."""

    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return redirect(f"{reverse('console:login')}?next={quote(request.get_full_path())}")
        if not user.can_use_console:
            return render(request, "dashboard/403.html", status=403)
        return view(request, *args, **kwargs)

    return wrapper
