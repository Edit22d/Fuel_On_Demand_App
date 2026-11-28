"""Response shapes for /api/v1 — one place so the Flutter models stay in sync."""
from __future__ import annotations

from core.models import Notification, Order, RiderProfile, Station, Transaction, User


def user_payload(user: User) -> dict:
    profile = getattr(user, "rider", None)
    data = {
        "id": user.pk,
        "name": user.name,
        "phone": user.phone,
        "email": user.email,
        "is_verified": user.is_verified,
        "role": user.role,
        "wallet_balance": user.wallet_balance,
        "points": user.points,
        "emergency_contact": user.emergency_contact,
        "initials": user.initials,
        "joined_at": user.date_joined.isoformat(),
    }
    if profile:
        data["rider"] = rider_payload(profile)
    return data


def rider_payload(profile: RiderProfile) -> dict:
    return {
        "status": profile.status,
        "vehicle_type": profile.vehicle_type,
        "plate": profile.plate,
        "online": profile.online,
        "rating": profile.rating,
        "deliveries_total": profile.deliveries_total,
        "earnings_total": profile.earnings_total,
        "lat": profile.lat,
        "lng": profile.lng,
        "reject_reason": profile.reject_reason,
    }


def station_payload(station: Station, *, with_prices: bool = True) -> dict:
    data = {
        "id": station.slug,
        "name": station.name,
        "brand": station.brand,
        "brand_label": station.get_brand_display(),
        "address": station.address,
        "lat": station.lat,
        "lng": station.lng,
        "rating": station.rating,
        "reviews": station.reviews,
        "is_active": station.is_active,
        "opens_24h": station.opens_24h,
        "service_radius_km": station.service_radius_km,
    }
    if with_prices:
        data["prices"] = station.price_map
        data["price_list"] = [
            {"fuel_type": p.fuel_type, "price": p.price, "delta": p.delta, "updated_at": p.updated_at.isoformat()}
            for p in station.prices.all()
        ]
    return data


def order_payload(order: Order, *, with_events: bool = False, with_tracking: bool = False) -> dict:
    data = {
        "id": order.pk,
        "number": order.number,
        "status": order.status,
        "status_label": order.get_status_display(),
        "is_active": order.is_active,
        "station": {"id": order.station.slug, "name": order.station.name, "brand": order.station.brand},
        "rider": {"id": order.rider_id, "name": order.rider.name, "phone": order.rider.phone, "rating": getattr(order.rider, "rider", None) and order.rider.rider.rating}
        if order.rider
        else None,
        "fuel_type": order.fuel_type,
        "litres": float(order.litres),
        "unit_price": order.unit_price,
        "fuel_total": order.fuel_total,
        "delivery_fee": order.delivery_fee,
        "service_fee": order.service_fee,
        "total": order.total,
        "payment_method": order.payment_method,
        "payment_status": order.payment_status,
        "delivery_address": order.delivery_address,
        "lat": order.lat,
        "lng": order.lng,
        "note": order.note,
        "distance_km": order.distance_km,
        "eta_minutes": order.eta_minutes,
        "delivery_code": order.delivery_code if order.status in {"arrived", "delivered"} else None,
        "rating": order.rating,
        "review": order.review,
        "created_at": order.created_at.isoformat(),
        "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
        "cancelled_at": order.cancelled_at.isoformat() if order.cancelled_at else None,
        "cancel_reason": order.cancel_reason,
    }
    if with_events:
        data["events"] = [
            {"status": e.status, "note": e.note, "at": e.created_at.isoformat()} for e in order.events.all()
        ]
    if with_tracking:
        latest = order.pings.first()
        data["tracking"] = {
            "rider": {"lat": order.rider.rider.lat if order.rider and hasattr(order.rider, "rider") else None,
                      "lng": order.rider.rider.lng if order.rider and hasattr(order.rider, "rider") else None},
            "last_ping": {"lat": latest.lat, "lng": latest.lng, "at": latest.created_at.isoformat()} if latest else None,
            "destination": {"lat": order.lat, "lng": order.lng},
            "eta_minutes": order.eta_minutes,
        }
    return data


def transaction_payload(tx: Transaction) -> dict:
    return {
        "id": tx.pk,
        "kind": tx.kind,
        "method": tx.method,
        "amount": tx.amount,
        "status": tx.status,
        "reference": tx.reference,
        "note": tx.note,
        "order": tx.order.number if tx.order else None,
        "created_at": tx.created_at.isoformat(),
    }


def notification_payload(note: Notification) -> dict:
    return {
        "id": note.pk,
        "title": note.title,
        "body": note.body,
        "kind": note.kind,
        "is_read": note.is_read,
        "created_at": note.created_at.isoformat(),
    }
