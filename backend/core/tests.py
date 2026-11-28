"""Behavioural tests for the shared business rules in `core.services`."""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from core.models import (
    FuelPrice,
    Order,
    RiderProfile,
    Station,
    StationStock,
    Tanker,
    TankerTrip,
    Transaction,
    User,
)
from core.services import (
    DomainError,
    accept_trip,
    advance_order,
    arrive_trip,
    assign_rider,
    cancel_order,
    complete_trip,
    create_order,
    create_trip,
    depart_trip,
    load_trip,
    offload_trip,
    quote,
    set_tanker_status,
)


class ServiceTestCase(TestCase):
    def setUp(self):
        self.station = Station.objects.create(
            slug="test-station",
            name="Test Station",
            brand="hashi",
            address="Kampala",
            lat=0.3392,
            lng=32.5931,
        )
        FuelPrice.objects.create(station=self.station, fuel_type="petrol", price=6800)
        self.customer = User.objects.create_user(phone="+256700111222", name="Test Customer", role="customer")
        self.rider_user = User.objects.create_user(phone="+256700111333", name="Test Rider", role="rider")
        RiderProfile.objects.create(
            user=self.rider_user, status="approved", plate="UAA 001A", vehicle_type="boda"
        )

    def _order(self, **overrides):
        payload = dict(
            customer=self.customer,
            station=self.station,
            fuel_type="petrol",
            litres=10,
            payment_method=Order.PaymentMethod.MOMO,
            delivery_address="Kololo, Kampala",
            lat=0.3476,
            lng=32.5975,
        )
        payload.update(overrides)
        return create_order(**payload)

    def test_quote_totals_add_up(self):
        priced = quote(self.station, "petrol", 10, 0.3476, 32.5975)
        self.assertEqual(priced["litres"], Decimal("10.0"))
        self.assertEqual(priced["fuel_total"], 68_000)
        self.assertEqual(
            priced["total"], priced["fuel_total"] + priced["delivery_fee"] + priced["service_fee"]
        )
        self.assertGreater(priced["delivery_fee"], 0)
        self.assertGreater(priced["eta_minutes"], 0)

    def test_quote_rejects_unknown_fuel(self):
        with self.assertRaises(Exception):
            quote(self.station, "kerosene", 10)

    def test_sandbox_payment_confirms_the_order(self):
        order = self._order()
        self.assertEqual(order.status, Order.Status.CONFIRMED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertTrue(
            Transaction.objects.filter(order=order, kind=Transaction.Kind.PAYMENT).exists()
        )

    def test_full_delivery_flow_settles_rider_pay(self):
        order = self._order()
        assign_rider(order, self.rider_user)
        advance_order(order, Order.Status.PICKED_UP)
        advance_order(order, Order.Status.ARRIVED)
        advance_order(order, Order.Status.DELIVERED)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.DELIVERED)
        self.assertIsNotNone(order.delivered_at)
        self.assertTrue(
            Transaction.objects.filter(order=order, kind=Transaction.Kind.EARNING).exists()
        )
        profile = RiderProfile.objects.get(pk=self.rider_user.rider.pk)
        self.assertEqual(profile.deliveries_total, 1)
        self.assertGreater(profile.earnings_total, 0)

    def test_state_machine_rejects_skipped_steps(self):
        order = self._order()
        assign_rider(order, self.rider_user)
        with self.assertRaises(Exception):
            advance_order(order, Order.Status.ARRIVED)

    def test_cancel_refunds_a_paid_order(self):
        order = self._order()
        cancel_order(order, "Changed my mind")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.REFUNDED)
        self.assertTrue(
            Transaction.objects.filter(order=order, kind=Transaction.Kind.REFUND).exists()
        )


class TankerTripTests(TestCase):
    """Bulk fuel movement: assignment, the trip state machine and reconciliation."""

    def setUp(self):
        self.station = Station.objects.create(
            slug="fleet-station", name="Fleet Station", brand="total",
            address="Kampala", lat=0.34, lng=32.58,
        )
        FuelPrice.objects.create(station=self.station, fuel_type="petrol", price=6800)
        self.driver = User.objects.create_user(
            phone="+256700222333", name="Truck Driver", role="tanker"
        )
        self.tanker = Tanker.objects.create(
            plate="UAX 100X", make="MAN", model_name="TGX 26.440",
            capacity_litres=20000, driver=self.driver,
            home_station=self.station, status=Tanker.Status.ACTIVE, is_verified=True,
        )

    def _trip(self, litres=10000):
        return create_trip(
            tanker=self.tanker, station=self.station, fuel_type="petrol", litres=litres
        )

    def test_trip_credits_station_stock_and_records_variance(self):
        trip = self._trip()
        self.assertEqual(trip.status, TankerTrip.Status.ASSIGNED)
        accept_trip(trip)
        load_trip(trip, 9950)
        depart_trip(trip)
        arrive_trip(trip)
        offload_trip(trip, 9900)
        stock = StationStock.objects.get(station=self.station, fuel_type="petrol")
        self.assertEqual(stock.litres, 9900)
        complete_trip(trip)
        trip.refresh_from_db()
        self.assertEqual(trip.status, TankerTrip.Status.COMPLETED)
        self.assertEqual(trip.variance_litres, 50)
        self.assertEqual(trip.variance_pct, 0.5)

    def test_a_truck_can_only_hold_one_open_trip(self):
        self._trip()
        with self.assertRaises(DomainError):
            self._trip()

    def test_load_cannot_exceed_truck_capacity(self):
        trip = self._trip()
        accept_trip(trip)
        with self.assertRaises(DomainError):
            load_trip(trip, 25000)

    def test_steps_must_run_in_order(self):
        trip = self._trip()
        with self.assertRaises(DomainError):
            depart_trip(trip)

    def test_suspending_a_loaded_truck_is_blocked(self):
        self._trip()
        with self.assertRaises(DomainError):
            set_tanker_status(self.tanker, "suspended")

    def test_stock_level_tracks_capacity(self):
        station = self.station
        StationStock.objects.create(
            station=station, fuel_type="diesel", litres=1500, capacity_litres=10000
        )
        stock = StationStock.objects.get(station=station, fuel_type="diesel")
        self.assertEqual(stock.level_pct, 15)
        self.assertTrue(stock.is_low)
