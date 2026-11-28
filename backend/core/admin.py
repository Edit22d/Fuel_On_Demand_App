"""Django admin — a fallback for superusers; day-to-day work happens in /console."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    AuditEvent,
    FuelPrice,
    Notification,
    Order,
    OrderEvent,
    OtpCode,
    RiderProfile,
    SavedPlace,
    Station,
    SupportTicket,
    TrackingPing,
    Transaction,
    User,
    Vehicle,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("-date_joined",)
    list_display = ("phone", "name", "role", "is_console_user", "is_suspended", "wallet_balance", "date_joined")
    list_filter = ("role", "is_console_user", "is_suspended", "is_active")
    search_fields = ("phone", "name", "email")
    fieldsets = (
        (None, {"fields": ("phone", "password")}),
        ("Profile", {"fields": ("name", "email", "role", "emergency_contact", "console_title")}),
        ("Wallet", {"fields": ("wallet_balance", "points", "referral_code")}),
        ("Access", {"fields": ("is_active", "is_staff", "is_console_user", "is_suspended", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("phone", "name", "password1", "password2", "role")}),)


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ("name", "brand", "address", "rating", "is_active")
    list_filter = ("brand", "is_active")
    search_fields = ("name", "address")


@admin.register(FuelPrice)
class FuelPriceAdmin(admin.ModelAdmin):
    list_display = ("station", "fuel_type", "price", "previous_price", "updated_at")
    list_filter = ("fuel_type",)


@admin.register(RiderProfile)
class RiderAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "vehicle_type", "online", "rating", "deliveries_total", "earnings_total")
    list_filter = ("status", "online", "vehicle_type")
    search_fields = ("user__name", "user__phone", "plate")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("number", "customer", "station", "fuel_type", "litres", "total", "status", "payment_status", "created_at")
    list_filter = ("status", "payment_status", "payment_method", "station")
    search_fields = ("number", "customer__phone", "customer__name")
    date_hierarchy = "created_at"
    readonly_fields = ("number", "created_at", "pickup_code", "delivery_code")


for model in (OrderEvent, TrackingPing, Transaction, Notification, SupportTicket, AuditEvent, OtpCode, Vehicle, SavedPlace):
    admin.site.register(model)
