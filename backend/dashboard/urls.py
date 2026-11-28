"""Console routes — every page lives under /console/."""
from django.urls import path

from . import views, views_comms, views_fleet, views_ops, views_reports

app_name = "console"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("live/", views.live, name="live"),

    path("orders/", views_ops.orders, name="orders"),
    path("orders/export/", views_ops.orders_export, name="orders_export"),
    path("orders/<int:pk>/", views_ops.order_detail, name="order_detail"),
    path("orders/<int:pk>/assign/", views_ops.order_assign, name="order_assign"),
    path("orders/<int:pk>/cancel/", views_ops.order_cancel, name="order_cancel"),
    path("orders/<int:pk>/advance/", views_ops.order_advance, name="order_advance"),

    path("stations/", views_ops.stations, name="stations"),
    path("stations/<slug:slug>/prices/", views_ops.station_prices, name="station_prices"),
    path("stations/<slug:slug>/toggle/", views_ops.station_toggle, name="station_toggle"),

    path("riders/", views_ops.riders, name="riders"),
    path("riders/<int:pk>/", views_ops.rider_detail, name="rider_detail"),
    path("riders/<int:pk>/action/", views_ops.rider_action, name="rider_action"),

    path("tankers/", views_fleet.tankers, name="tankers"),
    path("tankers/trips/new/", views_fleet.trip_create, name="trip_create"),
    path("tankers/trips/<int:pk>/<str:action>/", views_fleet.trip_action, name="trip_action"),
    path("tankers/<int:pk>/action/", views_fleet.tanker_action, name="tanker_action"),

    path("reports/", views_reports.reports, name="reports"),
    path("reports/export/", views_reports.reports_export, name="reports_export"),

    path("notifications/", views_comms.notifications, name="notifications"),
    path("notifications/broadcast/", views_comms.notification_broadcast, name="notification_broadcast"),
    path("notifications/<int:pk>/delete/", views_comms.notification_delete, name="notification_delete"),

    path("customers/", views_ops.customers, name="customers"),
    path("customers/<int:pk>/", views_ops.customer_detail, name="customer_detail"),
    path("customers/<int:pk>/action/", views_ops.customer_action, name="customer_action"),
    path("customers/<int:pk>/credit/", views_ops.customer_credit, name="customer_credit"),

    path("payments/", views_ops.payments, name="payments"),
    path("payments/export/", views_ops.payments_export, name="payments_export"),

    path("support/", views_ops.support, name="support"),
    path("support/<int:pk>/", views_ops.support_detail, name="support_detail"),
    path("support/<int:pk>/reply/", views_ops.support_reply, name="support_reply"),

    path("settings/", views_ops.settings_view, name="settings"),
    path("audit/", views_ops.audit_log, name="audit"),

    path("api/pulse/", views.api_pulse, name="api_pulse"),
    path("api/search/", views.api_search, name="api_search"),
]
