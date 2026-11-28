# FuelConnect — full stack

```
flutter_app/   Flutter frontend: customer app + rider app (all 52-screen prototype screens except the admin ones)
backend/       NestJS 11 API + Socket.IO tracking (the admin screens talk to the same API)
```

1. **Backend** → `backend/README.md` (Docker or local Postgres/PostGIS, `npm install`, `npm run db:setup`, `npm run start:dev`; Swagger at `/docs`).
2. **Flutter** → `flutter_app/README.md` for how to run, and `flutter_app/NEW_SCREENS.md` for what was added.

The backend is built to the contract the Flutter app already expects: port `8000`, `/api/v1`
prefix, `message` / `errors` error envelope, OTP 120 s / resend 30 s, `+256` phone
normalisation, payment aliases (`mtn`, `airtel`, `wallet`, `cash`) and the station `prices`
map. See `backend/README.md` section 12 for the integration snippets.

The Flutter app still runs on mocked data; the API is ready to be connected app-screen by
app-screen.
