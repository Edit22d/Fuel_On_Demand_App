---
kind: business_term
name: Business Glossary
category: business_term
scope:
    - '**'
---

### FuelConnect
- Definition：The project name for the full-stack on-demand fuel delivery platform comprising a Flutter customer/rider app, a NestJS backend API, and a built-in admin dashboard.
- Aliases：fuelconnect、FuelOnDemand

### admin dashboard
- Definition：A dependency-free static console served from `backend/public/dashboard/` under `/dashboard` on the NestJS server; staff login uses the same JWT pair as the mobile apps and grants access to orders, users, riders, stations, payments, withdrawals, support tickets, audit logs, and live deliveries.
- Aliases：console、operations console

### withdrawals
- Definition：Rider payout requests submitted via `POST /rider/withdrawals` (minimum UGX 10,000); admins approve/reject/process them through `GET/POST /admin/withdrawals`. The queue is empty until a rider's wallet balance reaches the threshold.
- Aliases：payouts、payout request

### revenueSeries
- Definition：Admin stats field containing exactly seven entries ordered oldest → today, where `day` is a plain `YYYY-MM-DD` label in the database session timezone and days without orders carry `revenue: 0, orders: 0`; today's bucket must match `revenue.today`.
- Aliases：revenue series、7-day revenue chart

### Idempotency-Key
- Definition：A UUID sent in the `Idempotency-Key` header on `POST /orders` (and honoured on payment retries) so repeated requests return the original order instead of creating duplicates; settlement itself is idempotent.
- Aliases：idempotency key

### request log
- Definition：The floating bottom-right panel in the admin dashboard that records every call the console makes (method, path, status, ms), used as a quick smoke test of the API during development.
- Aliases：request log panel
