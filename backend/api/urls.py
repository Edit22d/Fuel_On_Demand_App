"""The /api/v1 contract used by the Flutter customer + rider apps."""
from django.urls import path

from . import views_auth as auth
from . import views_customer as customer
from . import views_rider as rider

urlpatterns = [
    # auth + profile
    path("auth/register", auth.register),
    path("auth/login", auth.login),
    path("auth/otp/send", auth.otp_send),
    path("auth/otp/verify", auth.otp_verify),
    path("auth/forgot", auth.forgot),
    path("auth/reset", auth.reset),
    path("auth/logout", auth.logout),
    path("me", auth.me),

    # stations
    path("stations", customer.stations),
    path("stations/<slug:slug>", customer.station_detail),

    # garage + places
    path("vehicles", customer.vehicles),
    path("vehicles/<int:pk>", customer.vehicle_detail),
    path("places", customer.places),
    path("places/<int:pk>", customer.place_detail),

    # orders
    path("orders", customer.orders),
    path("orders/quote", customer.order_quote),
    path("orders/<int:pk>", customer.order_detail),
    path("orders/<int:pk>/tracking", customer.order_tracking),
    path("orders/<int:pk>/cancel-preview", customer.order_cancel_preview),
    path("orders/<int:pk>/cancel", customer.order_cancel),
    path("orders/<int:pk>/rate", customer.order_rate),

    # wallet
    path("wallet", customer.wallet),
    path("wallet/transactions", customer.wallet_transactions),
    path("wallet/topup", customer.wallet_topup),

    # notifications
    path("notifications", customer.notifications),
    path("notifications/read-all", customer.notifications_read_all),
    path("notifications/<int:pk>/read", customer.notification_read),

    # rider
    path("rider/register", rider.rider_register),
    path("rider/login", rider.rider_login),
    path("rider/status", rider.rider_status),
    path("rider/location", rider.rider_location),
    path("rider/dashboard", rider.rider_dashboard),
    path("rider/deliveries", rider.rider_deliveries),
    path("rider/deliveries/active", rider.rider_active),
    path("rider/deliveries/<int:pk>", rider.rider_delivery_detail),
    path("rider/deliveries/<int:pk>/accept", rider.rider_delivery_accept),
    path("rider/deliveries/<int:pk>/reject", rider.rider_delivery_reject),
    path("rider/deliveries/<int:pk>/pickup", rider.rider_pickup),
    path("rider/deliveries/<int:pk>/arrived", rider.rider_arrived),
    path("rider/deliveries/<int:pk>/deliver", rider.rider_deliver),
    path("rider/earnings", rider.rider_earnings),
    path("rider/withdraw", rider.rider_withdraw),

    # payments
    path("payments/webhook/<str:provider>", rider.payment_webhook),
]
