---
kind: external_dependency
name: MTN MoMo & Airtel Money payment providers
slug: mtn-momo-airtel-money
category: external_dependency
category_hints:
    - sdk_real_api
    - auth_protocol
scope:
    - '**'
---

### Identity
Ugandan mobile-money providers MTN (`/collection/v1_0/requesttopay`) and Airtel (`/merchant/v1/payments/`) are wired as pluggable payment providers behind `MobileMoneyProvider`.

### Role in this repo
- Payment method aliases `mtn`/`mtn_momo`/`momo` map to `MTN_MOMO`; `airtel`/`airtel_money` map to `AIRTEL_MONEY`.
- In production the provider makes outbound HTTP calls; in sandbox (`PAYMENTS_SANDBOX=true`) the client calls `POST /payments/:id/simulate` instead.
- Provider callbacks arrive at `POST /api/v1/payments/webhooks/:provider` and must carry `x-payments-signature` = HMAC-SHA256 of the RAW body keyed by `PAYMENT_WEBHOOK_SECRET`, verified with `timingSafeEqual`.

### Integration notes
- Credentials go in `.env` as `MTN_MOMO_*` / `AIRTEL_MONEY_*`; set `PAYMENTS_SANDBOX=false` and point each provider's callback URL at `<host>/api/v1/payments/webhooks/mtn` (or `.../airtel`).
- Duplicate callbacks return `{ status: "duplicate" }`; amount mismatches are flagged `PAYMENT_AMOUNT_MISMATCH` in audit rather than silently dropped.
- Verify exact provider endpoint URLs and signature headers against the official docs before enabling live mode.