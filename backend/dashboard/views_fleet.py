"""Tanker / truck management: fleet, bulk trips and fuel reconciliation."""
from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import FuelPrice, Station, StationStock, Tanker, TankerTrip, User
from core.services import (
    DomainError,
    accept_trip,
    arrive_trip,
    audit,
    cancel_trip,
    complete_trip,
    create_trip,
    depart_trip,
    load_trip,
    offload_trip,
    set_tanker_status,
)

from .decorators import console_required


@console_required
def tankers(request):
    fleet_status = request.GET.get("status", "")
    trip_status = request.GET.get("trip_status", "active")

    fleet = Tanker.objects.select_related("driver", "home_station").prefetch_related("trips")
    if fleet_status:
        fleet = fleet.filter(status=fleet_status)

    trips = TankerTrip.objects.select_related("tanker", "driver", "station")
    if trip_status == "active":
        trips = trips.filter(status__in=TankerTrip.ACTIVE_STATUSES)
    elif trip_status:
        trips = trips.filter(status=trip_status)

    week_ago = timezone.now() - timedelta(days=7)
    settled = TankerTrip.objects.filter(status=TankerTrip.Status.COMPLETED, completed_at__gte=week_ago)
    variance = sum(trip.variance_litres for trip in settled)

    stats = {
        "fleet": Tanker.objects.count(),
        "active": Tanker.objects.filter(status=Tanker.Status.ACTIVE).count(),
        "open_trips": TankerTrip.objects.filter(status__in=TankerTrip.ACTIVE_STATUSES).count(),
        "in_transit": TankerTrip.objects.filter(status=TankerTrip.Status.IN_TRANSIT).count(),
        "litres_7d": TankerTrip.objects.filter(offloaded_at__gte=week_ago).aggregate(
            total=Sum("received_litres")
        )["total"] or 0,
        "variance_7d": variance,
        "unverified": Tanker.objects.filter(is_verified=False).count(),
    }

    stock = StationStock.objects.select_related("station").order_by("station__name", "fuel_type")
    low_stock = [row for row in stock if row.is_low]

    return render(request, "dashboard/tankers.html", {
        "active_nav": "tankers",
        "page_title": "Tankers & bulk trips",
        "page_eyebrow": f"{stats['fleet']} trucks on the roster",
        "fleet": fleet,
        "trips": trips,
        "stats": stats,
        "stock": stock,
        "low_stock": low_stock,
        "drivers": User.objects.filter(role="tanker", is_suspended=False).order_by("name"),
        "stations": Station.objects.filter(is_active=True),
        "fuel_types": FuelPrice.FuelType.choices,
        "fleet_statuses": Tanker.Status.choices,
        "trip_statuses": TankerTrip.Status.choices,
        "filters": {"status": fleet_status, "trip_status": trip_status},
        "available_tankers": [t for t in Tanker.objects.select_related("driver").filter(
            is_verified=True, status__in=[Tanker.Status.ACTIVE, Tanker.Status.IDLE]
        ) if not t.trips.filter(status__in=TankerTrip.ACTIVE_STATUSES).exists()],
    })


@console_required
@require_POST
def tanker_action(request, pk):
    tanker = get_object_or_404(Tanker, pk=pk)
    op = request.POST.get("op", "")
    try:
        if op == "verify":
            tanker.is_verified = not tanker.is_verified
            tanker.save(update_fields=["is_verified", "updated_at"])
            audit(request, "tanker.verified" if tanker.is_verified else "tanker.unverified", target=tanker.plate)
            messages.success(request, f"{tanker.plate} {'verified' if tanker.is_verified else 'unverified'}.")
        elif op == "status":
            set_tanker_status(tanker, request.POST.get("status", ""), actor=request.user)
            messages.success(request, f"{tanker.plate} is now {tanker.get_status_display().lower()}.")
        elif op == "driver":
            driver_id = request.POST.get("driver") or ""
            driver = User.objects.filter(pk=driver_id, role="tanker").first() if driver_id else None
            tanker.driver = driver
            tanker.save(update_fields=["driver", "updated_at"])
            audit(request, "tanker.driver", target=tanker.plate, driver=driver.name if driver else None)
            messages.success(request, f"{tanker.plate}: driver set to {driver.name if driver else 'nobody'}.")
        else:
            raise DomainError("Unknown action.")
    except DomainError as exc:
        messages.error(request, str(exc))
    return redirect("console:tankers")


@console_required
@require_POST
def trip_create(request):
    tanker = get_object_or_404(Tanker, pk=request.POST.get("tanker") or 0)
    station = get_object_or_404(Station, pk=request.POST.get("station") or 0)
    try:
        trip = create_trip(
            tanker=tanker,
            station=station,
            fuel_type=request.POST.get("fuel_type") or FuelPrice.FuelType.DIESEL,
            litres=request.POST.get("litres"),
            origin=(request.POST.get("origin") or "").strip(),
            notes=(request.POST.get("notes") or "").strip(),
            actor=request.user,
        )
    except DomainError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            f"{trip.reference}: {trip.assigned_litres:,} L of {trip.fuel_type} "
            f"assigned to {tanker.plate} for {station.name}.",
        )
    return redirect("console:tankers")


@console_required
@require_POST
def trip_action(request, pk, action):
    trip = get_object_or_404(TankerTrip.objects.select_related("tanker", "station"), pk=pk)
    try:
        if action == "accept":
            accept_trip(trip, actor=request.user)
        elif action == "load":
            load_trip(trip, request.POST.get("litres"), actor=request.user)
        elif action == "depart":
            depart_trip(trip, actor=request.user)
        elif action == "arrive":
            arrive_trip(trip, actor=request.user)
        elif action == "offload":
            offload_trip(trip, request.POST.get("litres"), actor=request.user)
        elif action == "complete":
            complete_trip(trip, actor=request.user)
        elif action == "cancel":
            cancel_trip(trip, actor=request.user, reason=request.POST.get("reason", ""))
        else:
            raise DomainError("Unknown trip action.")
    except DomainError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"{trip.reference} is now {trip.get_status_display().lower()}.")
    return redirect("console:tankers")
