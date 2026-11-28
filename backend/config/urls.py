"""Root URL configuration.

/api/v1/*   JSON contract for the Flutter customer + rider apps
/console/*  Staff operations console (the dashboard)
/admin/*    Django admin, locked to superusers
"""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health(_request):
    return JsonResponse({"status": "ok", "service": "fuelondemand", "version": "1.0.0"})


urlpatterns = [
    path("", health, name="health"),
    path("api/v1/", include("api.urls")),
    path("console/", include("dashboard.urls")),
    path("admin/", admin.site.urls),
]

handler403 = "dashboard.views.error_403"
handler404 = "dashboard.views.error_404"
handler500 = "dashboard.views.error_500"
