---
kind: external_dependency
name: Socket.IO real-time tracking
slug: socketio
category: external_dependency
category_hints:
    - framework_behavior
scope:
    - '**'
---

### Identity
Socket.IO (NestJS `@nestjs/platform-socket.io` + `@nestjs/websockets`) powers the live delivery tracking channel.

### Role in this repo
- Namespace `/tracking` under the same Nest server that serves REST (`PORT 8000`).
- Authentication happens in the handshake via `{ token }` or `Authorization` header; invalid sessions are disconnected.
- Clients subscribe per order (`order:subscribe`) and per operations feed (`admin:subscribe`); riders emit `rider:location` throttled by `TRACKING_MIN_INTERVAL_MS`.

### Stable integration shape
- Connect to `<host>/tracking` with auth token in the handshake.
- On reconnect, re-emit `order:subscribe` and restart the GPS stream because rooms are lost.
- Rider location payloads include `orderId, lat, lng, speedKph?, heading?, accuracyM?`; only a rider with an ACCEPTED assignment on that order may push coordinates for it.
- Verify exact event names and payload shapes against the README section 11 contract rather than inferring from source.