---
kind: configuration_system
name: NestJS ConfigModule with Joi Validation and Typed AppConfig
category: configuration_system
scope:
    - '**'
source_files:
    - backend/src/config/configuration.ts
    - backend/src/config/env.validation.ts
    - backend/src/app.module.ts
    - backend/src/main.ts
    - backend/.env.example
---

## Overview

The FuelConnect backend uses **NestJS `@nestjs/config`** (`ConfigModule`) as its configuration system. Configuration is loaded from `.env` files, validated against a Joi schema, and exposed through a single typed `AppConfig` object consumed via `ConfigService` across the application.

## Key Files

- `backend/src/config/configuration.ts` — defines the `AppConfig` TypeScript interface and the default loader function that maps `process.env` values into typed config objects (with `int()` / `bool()` helpers).
- `backend/src/config/env.validation.ts` — Joi validation schema for every environment variable, including required fields, ranges, and defaults.
- `backend/.env.example` — copyable template documenting every supported env var with comments.
- `backend/.env` — local development secrets (not committed; listed in `.gitignore`).
- `backend/src/app.module.ts` — registers `ConfigModule.forRoot({ load: [configuration], validationSchema: envValidationSchema })` globally.
- `backend/src/main.ts` — reads `env`, `port`, `apiPrefix`, `corsOrigins` from `ConfigService` to bootstrap NestJS.

## Architecture and Conventions

### Two-layer loading

1. **Joi validation layer** (`env.validation.ts`): runs at module initialization. It enforces types, ranges, and presence of critical variables (e.g. `DATABASE_URL` required, `JWT_SECRET` min 32 chars, `PAYMENT_WEBHOOK_SECRET` min 8 chars). The schema uses `allowUnknown: true` so unknown env vars are silently ignored rather than causing startup failure.
2. **Typed mapping layer** (`configuration.ts`): after Joi passes, the exported default function builds an `AppConfig` object. It uses two small helpers:
   - `int(value, fallback)` — parses integers with `Number.parseInt` and falls back to a default if not finite.
   - `bool(value, fallback)` — treats `'1' | 'true' | 'yes' | 'on'` (case-insensitive) as truthy; otherwise returns the fallback.

This means the same value can be read safely from either layer: Joi validates it at startup, and `configuration.ts` provides sensible runtime defaults.

### Grouped configuration sections

`AppConfig` groups related settings under nested objects:
- `jwt` — secret, access/refresh/reset TTLs.
- `otp` — TTL, resend interval, max attempts, dev mode.
- `pricing` — delivery fees, rider commission, dispatch radius, assignment timeout.
- `payments` — webhook secret, sandbox flag, MTN Mobile Money and Airtel Money provider credentials.
- `tracking` — minimum interval and history retention.

Modules consume these via `ConfigService.get('jwt.secret')`, `ConfigService.get('pricing.deliveryBaseFee')`, etc., rather than reading raw env vars directly.

### Environment-specific behavior

- `NODE_ENV` drives OTP dev mode: `OTP_DEV_MODE` defaults to `true` when `NODE_ENV !== 'production'`.
- CORS behavior in `main.ts`: if `CORS_ORIGINS` is empty in production, a warning is logged and all origins are allowed (a deliberate safety valve).
- Payment providers have a `sandbox` flag (`PAYMENTS_SANDBOX`) that toggles simulated provider mode.

### Secrets handling

- JWT secret has a hardcoded development fallback: `'dev-only-secret-change-me-please-1234567890'`.
- Payment webhook secret has a hardcoded fallback: `'dev-webhook-secret'`.
- Provider API keys (MTN, Airtel) default to empty strings.
- `.env` is gitignored; `.env.example` documents the full set of variables with inline comments explaining each one.

### Bootstrapping

`AppModule` registers `ConfigModule.forRoot` with:
- `isGlobal: true` — available everywhere without per-module imports.
- `cache: true` — config is cached after first resolution.
- `load: [configuration]` — the typed config factory.
- `validationSchema: envValidationSchema` — Joi schema.
- `validationOptions: { abortEarly: false, allowUnknown: true }` — report all validation errors at once, ignore unknown env vars.

`main.ts` then retrieves `env`, `port`, `apiPrefix`, `corsOrigins` from `ConfigService` to configure Helmet, CORS, global prefix, static assets, Swagger, and the listening port.

## Conventions and Constraints

- Every environment variable used by the app is declared in both `env.validation.ts` (Joi schema) and `configuration.ts` (typed mapping); adding a new setting requires updating both files.
- Required variables are enforced by Joi: `DATABASE_URL`, `JWT_SECRET`, and `PAYMENT_WEBHOOK_SECRET` are marked `.required()` and will cause startup to fail if missing.
- Numeric env vars use the `int()` helper, which rejects non-finite values and falls back to documented defaults (e.g. `PORT=8000`, `JWT_ACCESS_TTL=900`, `DELIVERY_BASE_FEE=8000`).
- Boolean env vars accept only the four string literals `'1'`, `'true'`, `'yes'`, `'on'` (case-insensitive); anything else is treated as falsy.
- Unknown environment variables are allowed but ignored (`allowUnknown: true`), so extra vars do not break startup.
- The `.env.example` file is the authoritative documentation of supported variables, with comments describing each section (Database, Redis, JWT, OTP, Pricing, Payments, Tracking).
- Production hardening rules visible in code: `JWT_SECRET` must be ≥ 32 characters, `PAYMENT_WEBHOOK_SECRET` must be ≥ 8 characters, `OTP_MAX_ATTEMPTS` is capped at 10, `RIDER_COMMISSION_PERCENT` is capped at 100.