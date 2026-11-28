"""Console access-control and JSON API contract tests."""
from __future__ import annotations

from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from core.models import FuelPrice, Notification, Station, Tanker, TankerTrip, User

PASSWORD = "Testing@2026"


class ConsoleAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(
            phone="+256700900001",
            password=PASSWORD,
            name="Console Operator",
            role="staff",
            is_staff=True,
            is_console_user=True,
        )
        cls.customer = User.objects.create_user(
            phone="+256700900002", password=PASSWORD, name="Plain Customer", role="customer"
        )

    def test_anonymous_visitor_is_redirected_to_login(self):
        response = self.client.get("/console/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/console/login/", response["Location"])

    def test_customer_without_console_rights_gets_403(self):
        self.client.force_login(self.customer)
        response = self.client.get("/console/")
        self.assertEqual(response.status_code, 403)

    def test_console_user_can_open_the_overview(self):
        self.client.force_login(self.staff)
        response = self.client.get("/console/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "chart-series")
        self.assertContains(response, "data-map")
        self.assertEqual(response["Cache-Control"], "no-store, no-cache, must-revalidate, max-age=0")

    def test_every_console_screen_renders_for_staff(self):
        self.client.force_login(self.staff)
        for path in [
            "/console/live/",
            "/console/orders/",
            "/console/stations/",
            "/console/riders/",
            "/console/customers/",
            "/console/payments/",
            "/console/support/",
            "/console/settings/",
            "/console/audit/",
            "/console/tankers/",
            "/console/reports/",
            "/console/notifications/",
        ]:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_logout_ends_the_session(self):
        self.client.force_login(self.staff)
        response = self.client.post("/console/logout/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/console/").status_code, 302)


class ApiContractTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        station = Station.objects.create(
            slug="api-station", name="API Station", brand="shell", address="Kampala", lat=0.34, lng=32.58
        )
        from core.models import FuelPrice

        FuelPrice.objects.create(station=station, fuel_type="petrol", price=6900)
        cls.station = station
        cls.customer = User.objects.create_user(phone="+256700900003", name="API Customer", role="customer")

    def test_health_endpoint(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_stations_are_public(self):
        response = self.client.get("/api/v1/stations")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(len(response.json()["stations"]), 1)

    def test_orders_require_a_token(self):
        response = self.client.get("/api/v1/orders")
        self.assertEqual(response.status_code, 401)

    def test_quote_returns_a_priced_order(self):
        from api.security import issue_token

        token = issue_token(self.customer)
        response = self.client.post(
            "/api/v1/orders/quote",
            data={"station_id": self.station.slug, "fuel_type": "petrol", "litres": 10},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["quote"]["fuel_total"], 69_000)

    def test_customer_can_place_an_order(self):
        from api.security import issue_token

        token = issue_token(self.customer)
        response = self.client.post(
            "/api/v1/orders",
            data={
                "station_id": self.station.slug,
                "fuel_type": "petrol",
                "litres": 10,
                "payment_method": "momo",
                "delivery_address": "Kololo, Kampala",
                "delivery_lat": 0.3476,
                "delivery_lng": 32.5975,
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["order"]["status"], "confirmed")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AuthApiTests(TestCase):
    def setUp(self):
        cache.clear()
        mail.outbox.clear()

    def _register(self, **overrides):
        payload = {
            "name": "Integration Customer",
            "phone": "+256700912345",
            "email": "integration.customer@example.com",
            "password": "Fuel@2026",
        }
        payload.update(overrides)
        with patch.dict("api.views_auth.FC", {"otp_show_code": True, "otp_resend_seconds": 0}):
            return self.client.post("/api/v1/auth/register", data=payload, content_type="application/json")

    def test_registration_sends_confirmation_email_and_persists_account(self):
        response = self._register()
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data["otp_required"])
        self.assertEqual(data["purpose"], "signup")
        self.assertTrue(data["confirmation_sent"])
        self.assertEqual(data["delivery"]["channel"], "email")
        user = User.objects.get(phone="+256700912345")
        self.assertFalse(user.is_verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["integration.customer@example.com"])
        self.assertIn(data["dev_code"], mail.outbox[0].body)

    def test_confirmed_account_can_sign_in_later_with_same_credentials(self):
        registration = self._register().json()
        verified = self.client.post(
            "/api/v1/auth/otp/verify",
            data={"phone": "+256700912345", "purpose": "signup", "code": registration["dev_code"]},
            content_type="application/json",
        )
        self.assertEqual(verified.status_code, 200)
        self.assertTrue(verified.json()["user"]["is_verified"])

        with patch.dict("api.views_auth.FC", {"otp_on_login": False}):
            login = self.client.post(
                "/api/v1/auth/login",
                data={"phone": "0700912345", "password": "Fuel@2026"},
                content_type="application/json",
            )
        self.assertEqual(login.status_code, 200)
        self.assertIn("token", login.json())
        returning_client = Client()
        profile = returning_client.get(
            "/api/v1/me", HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}"
        )
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json()["user"]["email"], "integration.customer@example.com")

    def test_unverified_login_sends_signup_confirmation_instead_of_token(self):
        self._register()
        with patch.dict("api.views_auth.FC", {"otp_show_code": True, "otp_resend_seconds": 0}):
            response = self.client.post(
                "/api/v1/auth/login",
                data={"phone": "+256700912345", "password": "Fuel@2026"},
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["purpose"], "signup")
        self.assertNotIn("token", response.json())

    def test_duplicate_phone_and_email_are_rejected(self):
        self._register()
        self.assertEqual(self._register(phone="+256700912346").status_code, 422)
        self.assertEqual(self._register(email="another.customer@example.com").status_code, 422)
        self.assertEqual(User.objects.count(), 1)

    def test_password_reset_uses_the_confirmed_account(self):
        registration = self._register().json()
        self.client.post(
            "/api/v1/auth/otp/verify",
            data={"phone": "+256700912345", "purpose": "signup", "code": registration["dev_code"]},
            content_type="application/json",
        )
        with patch.dict("api.views_auth.FC", {"otp_show_code": True, "otp_resend_seconds": 0}):
            forgot = self.client.post(
                "/api/v1/auth/forgot",
                data={"phone": "+256700912345"},
                content_type="application/json",
            )
            verified = self.client.post(
                "/api/v1/auth/otp/verify",
                data={"phone": "+256700912345", "purpose": "reset", "code": forgot.json()["dev_code"]},
                content_type="application/json",
            )
        reset = self.client.post(
            "/api/v1/auth/reset",
            data={
                "phone": "+256700912345",
                "reset_token": verified.json()["reset_token"],
                "password": "NewFuel@2026",
                "password_confirmation": "NewFuel@2026",
            },
            content_type="application/json",
        )
        self.assertEqual(reset.status_code, 200)
        self.assertTrue(User.objects.get(phone="+256700912345").check_password("NewFuel@2026"))

    def test_flutter_web_origin_can_call_the_auth_api(self):
        response = self.client.options(
            "/api/v1/auth/login",
            HTTP_ORIGIN="http://127.0.0.1:5173",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type,authorization",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Access-Control-Allow-Origin"], "http://127.0.0.1:5173")


class FleetConsoleTests(TestCase):
    """Tanker management, the reports page and the broadcast desk."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(
            phone="+256700900010", password=PASSWORD, name="Fleet Admin",
            role="staff", is_staff=True, is_console_user=True,
        )
        cls.station = Station.objects.create(
            slug="console-station", name="Console Station", brand="stabex",
            address="Kampala", lat=0.34, lng=32.58,
        )
        FuelPrice.objects.create(station=cls.station, fuel_type="petrol", price=6800)
        cls.driver = User.objects.create_user(
            phone="+256700900011", name="Console Trucker", role="tanker"
        )
        cls.tanker = Tanker.objects.create(
            plate="UAX 200Y", make="Scania", model_name="R500",
            capacity_litres=20000, driver=cls.driver, home_station=cls.station,
            status=Tanker.Status.ACTIVE, is_verified=True,
        )

    def setUp(self):
        self.client.force_login(self.staff)

    def test_admin_can_run_a_trip_from_assignment_to_reconciliation(self):
        response = self.client.post("/console/tankers/trips/new/", {
            "tanker": self.tanker.pk, "station": self.station.pk,
            "fuel_type": "petrol", "litres": 12000, "origin": "Jinja depot",
        })
        self.assertEqual(response.status_code, 302)
        trip = TankerTrip.objects.get()
        self.client.post(f"/console/tankers/trips/{trip.pk}/accept/")
        self.client.post(f"/console/tankers/trips/{trip.pk}/load/", {"litres": 11900})
        for action in ["depart", "arrive"]:
            self.assertEqual(
                self.client.post(f"/console/tankers/trips/{trip.pk}/{action}/").status_code, 302
            )
        self.client.post(f"/console/tankers/trips/{trip.pk}/offload/", {"litres": 11850})
        self.client.post(f"/console/tankers/trips/{trip.pk}/complete/")
        trip.refresh_from_db()
        self.assertEqual(trip.status, TankerTrip.Status.COMPLETED)
        self.assertEqual(trip.received_litres, 11850)

    def test_duplicate_trip_is_refused_with_a_message(self):
        TankerTrip.objects.create(
            reference="TRP-TEST-001", tanker=self.tanker, driver=self.driver,
            station=self.station, fuel_type="petrol", assigned_litres=5000,
            status=TankerTrip.Status.ASSIGNED,
        )
        response = self.client.post(
            "/console/tankers/trips/new/",
            {"tanker": self.tanker.pk, "station": self.station.pk, "fuel_type": "petrol", "litres": 9000},
            follow=True,
        )
        self.assertEqual(TankerTrip.objects.count(), 1)
        self.assertContains(response, "open trip")

    def test_broadcast_reaches_only_the_chosen_segment(self):
        customer = User.objects.create_user(phone="+256700900012", name="Broadcast Customer", role="customer")
        User.objects.create_user(phone="+256700900013", name="Other Rider", role="rider")
        self.client.post("/console/notifications/broadcast/", {
            "audience": "customers", "kind": "promo",
            "title": "Price drop", "body": "Petrol is cheaper at every Stabex station this weekend.",
        })
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(Notification.objects.get().user, customer)

    def test_reports_page_and_csv_export(self):
        response = self.client.get("/console/reports/?period=30d")
        self.assertContains(response, "Daily breakdown")
        self.assertContains(response, "Bulk fuel reconciliation")
        export = self.client.get("/console/reports/export/?period=7d")
        self.assertEqual(export.status_code, 200)
        self.assertEqual(export["Content-Type"], "text/csv")
        self.assertIn("fuelondemand-7d-report", export["Content-Disposition"])
