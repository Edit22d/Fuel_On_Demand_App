---
kind: error_handling
name: NestJS Global Exception Filter with Prisma Error Mapping
category: error_handling
scope:
    - '**'
source_files:
    - backend/src/common/filters/all-exceptions.filter.ts
    - backend/src/app.module.ts
    - backend/src/auth/strategies/jwt.strategy.ts
    - backend/src/auth/auth.service.ts
    - backend/src/auth/otp.service.ts
    - backend/src/admin/admin.service.ts
    - backend/src/admin/admin-operations.service.ts
---

## Approach

The FuelConnect backend (NestJS) uses Nest's built-in exception system as its sole error-handling mechanism:
- Business and validation errors are raised by throwing Nest HTTP exceptions (`BadRequestException`, `UnauthorizedException`, `ForbiddenException`, `NotFoundException`, `ConflictException`, `InternalServerErrorException`) from service/strategy code.
- A single global `AllExceptionsFilter` (`backend/src/common/filters/all-exceptions.filter.ts`) catches every unhandled exception via `@Catch()` and converts it into a uniform JSON envelope.
- The filter is registered globally in `backend/src/app.module.ts` through `{ provide: APP_FILTER, useClass: AllExceptionsFilter }`.

There are no custom domain-specific error classes, no sentinel-error enum, no `try/catch` propagation of typed errors across layers, and no `panic`/`recover` analogues (this is not Go).

## Key Files

- `backend/src/common/filters/all-exceptions.filter.ts` — the only `ExceptionFilter`; centralizes status mapping, logging, and Prisma error translation.
- `backend/src/app.module.ts` — registers the filter globally via `APP_FILTER` provider.
- `backend/src/auth/strategies/jwt.strategy.ts` — throws `UnauthorizedException` for invalid/expired/suspended tokens.
- `backend/src/auth/auth.service.ts` — primary consumer of HTTP exceptions for auth flows (suspension, password mismatch, duplicate account).
- `backend/src/auth/otp.service.ts` — throws `BadRequestException` / `NotFoundException` for OTP lifecycle errors.
- `backend/src/admin/admin.service.ts`, `backend/src/admin/admin-operations.service.ts` — use `ForbiddenException` / `ConflictException` / `NotFoundException` for admin operations.

## Architecture & Conventions

### Uniform response envelope
Every error response follows this shape (defined as the local `ErrorBody` interface):
```json
{
  "statusCode": number,
  "error": string,          // human-readable label from STATUS_TEXT
  "message": string,        // user-facing message
  "errors"?: Record<string, string[]>,
  "path": string,
  "timestamp": string,
  "requestId"?: string
}
```
The comment on line 37–40 documents that the Flutter `ApiClient` reads `message` and the first entry of `errors` to build user-friendly copy.

### Status text map
A `STATUS_TEXT` dictionary (lines 22–35) maps numeric statuses to labels; unknown codes fall back to `'Error'`. It covers 400–429 plus 500/503.

### Exception classification inside the filter
1. `HttpException` — extract status and payload; if the payload is a string it becomes `message`; if it's an object, `body.message` (string or first element of an array) is used, and `body.errors` is forwarded verbatim.
2. `Prisma.PrismaClientKnownRequestError` — delegated to `mapPrismaError`, which translates known codes:
   - `P2002` → 409 `That <target> is already in use.`
   - `P2003` → 409 `This record is still referenced by other data.`
   - `P2025` → 404 `That record could not be found.`
   - any other code → 500 `A database error occurred. Please try again.`
3. `Prisma.PrismaClientValidationError` → 400 `The request contained an invalid value.`
4. Any other `Error` — logged at `error` level; defaults to 500 with the generic message.

### Logging policy
- For status ≥ 500: `logger.error(...)` including stack trace when available.
- For all other statuses: `logger.debug(...)`.
- Unhandled Prisma codes are additionally logged via `this.logger.error(`Unhandled Prisma error ${error.code}: ...`)`.

### Request correlation
The filter reads `request.id` (attached upstream, e.g. by middleware) and includes it as `requestId` in the response body when present.

### Where business logic raises errors
Services and strategies throw Nest HTTP exceptions directly rather than returning error objects or wrapping them in a custom type. Examples include:
- `auth.service.ts`: `UnauthorizedException` for wrong credentials, `ForbiddenException` for suspended accounts, `NotFoundException` for missing users, `BadRequestException` for password validation, `ConflictException` for duplicate email/phone.
- `otp.service.ts`: `BadRequestException` for expired/overused OTPs, `NotFoundException` for unknown phone numbers.
- `jwt.strategy.ts`: `UnauthorizedException` for invalid/expired/suspended sessions.
- `admin*.ts`: `ForbiddenException` for role checks, `ConflictException` for idempotency, `NotFoundException` for missing records.

## Conventions & Constraints

- **Single global filter**: All HTTP-layer errors flow through `AllExceptionsFilter` because it is registered via `APP_FILTER` in `app.module.ts`; there is no per-controller `@UseFilters(...)`. This is enforced by the module registration.
- **No custom exception hierarchy**: The codebase does not define subclasses of `HttpException` or domain error types; all thrown errors are Nest's built-in ones.
- **Prisma errors are never leaked to clients**: `PrismaClientKnownRequestError` is always translated through `mapPrismaError`, which returns either a mapped 4xx status or a safe 500 fallback — raw Prisma codes do not reach the API response.
- **User-facing messages come from the filter's `message` field**: The Flutter client consumes `message` (and optionally `errors[0]`), so service-level exceptions should put the user-facing text in the exception's message/payload, not in logs.
- **Validation payloads may carry structured errors**: Some services pass `{ message: [...] , errors: {...} }` objects to `BadRequestException` (e.g. `auth.service.ts:536`), which the filter forwards as the `errors` field in the envelope.
- **Status 401/403/404/409/429 preserve the original service message** (see the `if ([401,403,404,409,429].includes(status))` block); other statuses can be overridden by the filter's defaulting logic.