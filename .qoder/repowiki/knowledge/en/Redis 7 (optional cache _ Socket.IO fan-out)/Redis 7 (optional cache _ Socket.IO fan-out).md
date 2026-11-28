---
kind: external_dependency
name: Redis 7 (optional cache / Socket.IO fan-out)
slug: redis
category: external_dependency
category_hints:
    - client_constraint
scope:
    - '**'
---

### Identity
Redis 7 is an optional runtime dependency.

### Role in this repo
- OTP state, session refresh tokens, rate limiting, and rider location history live in Redis when configured.
- `@socket.io/redis-adapter` fans Socket.IO events across multiple NestJS instances; without it the gateway still works but only within a single process.

### Integration notes
- If `REDIS_URL` is empty the app falls back to in-process stores (single-instance dev). Docker Compose also spins `redis:7` alongside Postgres.
- When Redis is unavailable the API starts normally with `redis: disabled` in `/health`.