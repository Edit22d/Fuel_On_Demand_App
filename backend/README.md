# FuelOnDemand — Django backend + operations console

Backend for the FuelOnDemand Flutter app (customer + rider modes) and a premium
staff operations console that mirrors the app's dark-gold identity
(`ink #080A0C`, `panel #101317`, `gold #F5C72E`).

Everything on screen is database driven — KPIs, charts, maps, feeds and tables
all come from live queries; nothing is hard-coded in the templates.

```
config/      settings, root URLs, WSGI/ASGI
core/        domain models, business services, seed command, utilities
api/         /api/v1 JSON contract used by the Flutter apps (JWT bearer)
dashboard/   staff console: views, analytics, templates, static, middleware
```

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt

copy .env.example .env            # then edit the secrets
python manage.py migrate
python manage.py seed_demo        # --force to rebuild the demo dataset
python manage.py runserver 8000
```

* Console — <http://127.0.0.1:8000/console/>
* API root — <http://127.0.0.1:8000/>
* Django admin — <http://127.0.0.1:8000/admin/>

Demo console sign-in (created by `seed_demo`, change it in `.env` with
`FC_ADMIN_PASSWORD` before seeding a real environment):

| Role | Identifier | Password |
| --- | --- | --- |
| Head of Operations | `admin@fuelondemand.test` or `+256700000001` | `Console@2026` |
| Dispatch Lead | `dispatch@fuelondemand.test` | `Console@2026` |
| Finance Manager | `finance@fuelondemand.test` | `Console@2026` |

### Create your own console account

```bash
python manage.py create_console_user
```

Prompts for name, phone, optional email, job title and a password (8+ characters),
then creates a staff account that can sign in at `/console/` with **either the email
or the phone number**. The account, and any password reset, is written to the security log.

```bash
# non-interactive, with Django admin rights
python manage.py create_console_user --name "Jane Doe" --phone +256770123456 \
    --email jane@fuelondemand.test --title "Founder" --superuser

# reset the password of an existing operator
python manage.py create_console_user --phone +256770123456 --update
```

## The console

| Page | What it does |
| --- | --- |
| Overview `/console/` | 8 live KPIs with period deltas, revenue line chart, order-status donut, fuel-mix and payment donuts, top-station bars, top riders, live map, in-progress orders, activity feed, rider approvals, open tickets, latest ledger |
| Live board `/console/live/` | Large dispatch map, active deliveries, rider rail with freshness dots, delivery pipeline |
| Orders `/console/orders/` | Filter by query/status/station/method/day, sort, CSV export, paginated |
| Order detail | Timeline, status events, tracking pings, ledger, price breakdown, rider assignment, state-machine actions (`picked_up → arrived → delivered`), cancel with fee preview |
| Stations | Availability toggle, per-fuel price editing with automatic price history |
| Riders | Applications, suspension/reinstatement, deliveries and earnings, assigned order |
| Customers | Spend/order counts, wallet credit, suspension, order history |
| Tankers & trips `/console/tankers/` | Truck roster (plate, capacity, compartments, driver, verification, status), bulk trip board limited to `assigned  accepted  loaded  in transit  arrived  offloaded  reconciled`, per-step actions, station stock bars, low-stock alert and an assign-trip form |
| Payments | Inflow/outflow ledger with kind/status filters and CSV export |
| Reports `/console/reports/` | Daily / weekly / monthly / quarterly trading report: revenue, orders, litres, average order, delivery fees, completion, revenue trend, fuel mix, payment mix, station performance, rider leaderboard, bulk fuel reconciliation and a CSV download (`/console/reports/export/`) |
| Notifications `/console/notifications/` | Outbox of every push with type/audience filters, read state, delete, plus a broadcast desk that messages all customers, riders, tanker drivers, station staff or everyone |
| Support | Ticket inbox, priorities, replies and status changes |
| Settings | Service fee, delivery pricing, support line, banner announcement, payout schedule |
| Audit | Immutable security log (logins, lockouts, price changes, cancellations) |

Live behaviour: `console.js` polls `/console/api/pulse/` every few seconds and
repaints KPI values, delta chips, the map, active orders and the activity feed
without a page reload. `Ctrl/⌘ + K` opens the search palette backed by
`/console/api/search/`. Charts and the schematic Kampala map are hand-rolled SVG
(no CDN, no chart library) so the console also works fully offline.

## Bulk fuel (tanker) workflow

`core.services` owns the trip state machine and the station stock ledger:

```
create_trip  accept_trip  load_trip  depart_trip  arrive_trip
            offload_trip (credits StationStock)  complete_trip (reconciled)
```

Rules enforced server-side: one open trip per truck, litres within the truck's
capacity, steps must run in order, a truck with an open trip cannot be suspended,
and reconciliation records `variance_litres` / `variance_pct` (loaded  received)
plus a `warning` audit event whenever the two disagree.

## Security

* Custom user model keyed on phone; console access requires `is_console_user`
  **and** `is_staff` (`can_use_console`) — enforced by
  `ConsoleSecurityMiddleware` *and* the `console_required` view decorator.
* Anonymous `/console/*` requests are redirected to the branded login with
  `?next=`; accounts without console rights get a hard 403.
* Login throttling: 5 failed attempts per identifier/IP triggers a 15-minute
  cache-backed lockout; both success and failure are written to the audit log.
* Sessions expire after 30 minutes idle, are rotated on login, and every console
  response is sent `Cache-Control: no-store` + `X-Robots-Tag: noindex`.
* All mutations are POST-only, CSRF protected and produce an `AuditEvent`.
* Mobile API: JWT bearer tokens (`HS256`, 1 h), OTP send/verify with rate limits,
  role gates per endpoint, CSRF-exempt JSON envelope `{ok|message|errors}`.
* Production extras in `config/settings.py`: HSTS, SSL redirect, secure cookies,
  `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`,
  `clickjacking` protection — all toggled by `DJANGO_DEBUG`.

## API surface (`/api/v1`)

Auth: `auth/register`, `auth/login`, `auth/otp/send`, `auth/otp/verify`,
`auth/forgot`, `auth/reset`, `auth/logout`, `me`.

Catalogue: `stations`, `stations/<slug>`, `vehicles`, `vehicles/<pk>`,
`places`, `places/<pk>`.

Orders: `orders`, `orders/quote`, `orders/<pk>`, `orders/<pk>/tracking`,
`orders/<pk>/cancel-preview`, `orders/<pk>/cancel`, `orders/<pk>/rate`.

Wallet: `wallet`, `wallet/transactions`, `wallet/topup`.

Notifications: `notifications`, `notifications/read-all`,
`notifications/<pk>/read`.

Rider: `rider/register`, `rider/login`, `rider/status`, `rider/location`,
`rider/dashboard`, `rider/deliveries`, `rider/deliveries/active`,
`rider/deliveries/<pk>` (+ `/accept`, `/reject`, `/pickup`, `/arrived`,
`/deliver`), `rider/earnings`, `rider/withdraw`.

Payments: `payments/webhook/<provider>`.

## Business logic

All rules live in `core/services.py` and are shared by the API and the console:
quoting (fuel + distance-based delivery + service fee), order creation and
payment, rider assignment, the delivery state machine, settlement (rider pay,
commission, loyalty points), cancellations with fee windows, wallet ledger and
audit. Console forms can therefore never bypass a rule the apps rely on.

## Tests and checks

```bash
python manage.py check
python manage.py test
```

16 tests cover quoting, the order state machine, settlement, refunds, console
access control (redirect / 403 / no-store), every console screen rendering, and
the API contract including placing an order with a JWT.

The seed command is deterministic (fixed RNG seed) and produces 6 stations,
53 users, ~340 orders across two weeks, ledger entries, tickets, notifications
and a live window of in-flight deliveries so the live board is never empty.

## Deployment notes

Set `DJANGO_DEBUG=false`, a strong `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`
and real database credentials (`DB_ENGINE=postgres`), run `collectstatic`, then
serve with a WSGI server (gunicorn/waitress) behind TLS. Keep `FC_OTP_SHOW_CODE`
and the sandbox payment driver disabled outside development.