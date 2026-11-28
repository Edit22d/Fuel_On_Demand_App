---
kind: logging_system
name: NestJS Logger + AllExceptionsFilter (no structured logger, no frontend logging)
category: logging_system
scope:
    - '**'
source_files:
    - backend/src/main.ts
    - backend/src/common/filters/all-exceptions.filter.ts
    - backend/src/audit/audit.service.ts
    - backend/src/auth/otp.service.ts
    - backend/src/common/services/geo-location.service.ts
    - backend/src/payments/payments.service.ts
    - backend/src/payments/providers/mobile-money.provider.ts
    - backend/package.json
---

## What system/approach is used

The backend uses **NestJS built-in `Logger`** (`@nestjs/common`) — a simple console-based logger with contextual prefixes and five levels (`debug`, `log`, `warn`, `error`, `fatal`). There is no third-party structured logger (no Winston, Pino, Bunyan, etc.) in `backend/package.json`. The Flutter frontend has no dedicated logging library; it relies on Dart's standard `print()` / `debugPrint()` (none were found in the current codebase).

Log output goes straight to stdout/stderr via `console.log`/`console.error`; there is no file sink, log rotation, or remote ingestion configured.

## Key files and packages

- `backend/src/main.ts` — bootstrap entry point; creates a top-level `new Logger('Bootstrap')` and logs startup URLs and environment.
- `backend/src/common/filters/all-exceptions.filter.ts` — global `@Catch()` exception filter that centralizes error logging and maps Prisma errors to HTTP status codes.
- `backend/src/audit/audit.service.ts` — uses `Logger` to warn when audit writes fail.
- `backend/src/auth/otp.service.ts` — logs OTP verification codes at `log` level.
- `backend/src/common/services/geo-location.service.ts` — logs pruning counts and PostGIS write failures.
- `backend/src/payments/payments.service.ts` and `backend/src/payments/providers/mobile-money.provider.ts` — log payment-provider errors and warnings.
- `backend/prisma/seed.ts` — uses plain `console.log` for seed progress (not NestJS `Logger`).

No logging configuration file exists; the only environment-driven behavior is the production warning emitted when `CORS_ORIGINS` is empty.

## Architecture and conventions

1. **Per-class logger instances.** Every service/controller that logs instantiates its own `private readonly logger = new Logger('<ContextName>')` (e.g. `'Bootstrap'`, `'ExceptionFilter'`). This gives each log line a NestJS context prefix derived from the class name.
2. **Level usage pattern:**
   - `logger.log(...)` — informational lifecycle messages (startup URLs, OTP codes, pruning counts).
   - `logger.warn(...)` — recoverable misconfiguration or degraded state (empty CORS origins, mobile-money provider issues).
   - `logger.error(...)` — unrecoverable failures (Prisma write failures, unhandled exceptions, Prisma error codes not matched by the switch).
   - `logger.debug(...)` — request trace lines inside the exception filter for non-5xx responses.
3. **Centralized error envelope.** `AllExceptionsFilter` converts every thrown exception into a uniform JSON body:
   ```ts
   interface ErrorBody {
     statusCode: number;
     error: string;
     message: string;
     errors?: Record<string, string[]>;
     path?: string;
     timestamp: string;
     requestId?: string;
   }
   ```
   It also logs the full request method/URL/status/message plus stack traces for 5xx errors, while logging the same trace at `debug` level for lower statuses.
4. **Request correlation field.** The response body includes an optional `requestId` pulled from `request.id` (set upstream), but no middleware wiring this ID into the logger context was found in the inspected files.
5. **No structured fields beyond the envelope.** Log lines are plain strings interpolated with template literals; there is no JSON-structured log event model, no correlation IDs injected into every log line, and no log-level configuration via environment variables.
6. **Frontend side.** The Flutter app does not import any logging package; no `import 'logging'` or `import 'logger'` was found in `.dart` files.

## Conventions and constraints

- **Convention observed:** Each NestJS class that needs logging declares `private readonly logger = new Logger('<ClassName>');` and calls `this.logger.<level>(...)`. This is consistent across `main.ts`, `all-exceptions.filter.ts`, `audit.service.ts`, `otp.service.ts`, `geo-location.service.ts`, `payments.service.ts`, and `mobile-money.provider.ts`.
- **Convention observed:** Business-domain services use `log` for normal operational events and `error` for failures; `warn` is reserved for configuration/degradation signals.
- **Convention observed:** Unhandled database errors go through `mapPrismaError` in `AllExceptionsFilter`, which maps known Prisma error codes (`P2002`, `P2003`, `P2025`) to specific HTTP 4xx/5xx responses and falls back to `logger.error` + 500 for unknown codes.
- **Constraint enforced by the framework:** NestJS `Logger` routes all output to `console` under the hood; without a custom transport or `LoggerService` override, there is no way to change sinks or add structured serialization.
- **Constraint observed:** No log level is read from config/environment; debug/log/warn/error are all emitted regardless of deployment mode. Only the CORS-origin warning is gated on `env === 'production'`.
- **Not present:** No Winston/Pino/Bunyan integration, no structured log schema, no log rotation, no centralized log-level configuration, no correlation-id propagation into logger contexts.