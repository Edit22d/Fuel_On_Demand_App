# FuelOnDemand — Flutter frontend

On-demand fuel delivery app for Kampala, built with Flutter and styled after the
Cafu (Dubai) experience: dark `#080A0C` surfaces, a single gold `#F5C72E` accent,
Plus Jakarta Sans, and motion on every transition.

## Run it

```bash
flutter pub get
flutter run -d chrome          # or any emulator / device
flutter build web --release    # static site; serve it with `node serve_web.js`
```

`node serve_web.js [port]` serves `build/web` on `http://127.0.0.1:5173` with SPA
fallback, so deep links keep working without extra setup.

## Google Maps + GPS

The map layer is `lib/core/live_map.dart`. It renders real Google Maps tiles when a
key is available and otherwise falls back to a built-in dark map preview, so the app
never shows a broken surface.

Supply the key three ways, all from one value:

1. **Android** — put `MAPS_API_KEY=AIza...` in `android/local.properties` (or export
   `GOOGLE_MAPS_API_KEY`). `android/app/build.gradle.kts` injects it as the
   `com.google.android.geo.API_KEY` manifest placeholder.
2. **iOS** — set the `GOOGLE_MAPS_API_KEY` build setting (or put the key in
   `ios/Runner/Info.plist` under `GMSApiKey`). `AppDelegate.swift` registers it with
   `GMSServices`.
3. **Web** — build with `--dart-define=GOOGLE_MAPS_API_KEY=AIza...` and uncomment the
   Maps JavaScript API `<script>` in `web/index.html` using the same key.

`minSdk` is pinned to 23 for the maps SDK. Location permission strings are already
declared in `AndroidManifest.xml` and `ios/Runner/Info.plist`, and are requested at
runtime by `lib/services/location_service.dart`.

## Live tracking

`lib/services/tracking_service.dart` drives the tracking screen, the wallet's active
order card and the rider navigation map:

- With a bearer token present it polls the real API and reports `LIVE`.
- Without one it runs a clearly labelled `PREVIEW` simulation, so the UI can be
  reviewed offline. Nothing about this state leaks into production copy.

Backend contract:

```
GET  {baseUrl}/orders/{id}/tracking    -> OrderTracking.fromJson
POST {baseUrl}/orders/{id}/cancel
POST {baseUrl}/orders/{id}/delivered
```

## Backend integration seams

| Concern | File |
|---|---|
| HTTP + bearer token storage | `lib/services/api_client.dart` |
| Auth, OTP, password reset | `lib/services/auth_service.dart` |
| Live order tracking | `lib/services/tracking_service.dart` |
| GPS + reverse geocoding | `lib/services/location_service.dart` |
| Prices, wallet, rewards, order state | `lib/core/app_state.dart` |
| Rider jobs and earnings | `lib/core/rider_state.dart` |

`main()` calls `ApiClient.instance.init()` after `auth.init()`, so a restored token
immediately upgrades tracking from `PREVIEW` to `LIVE`.

## Dev-only affordances

`kShowDevOtp` in `lib/core/theme.dart` gates the local-only conveniences: the OTP
shown as a toast, the demo account hints and the rider demo credentials. Set it to
`false` for any build that talks to a real backend.

| Phone | Password | Role |
|---|---|---|
| `+256 700 123 456` | `Fuel@2025` | customer |
| `+256 701 234 567` | `Rider@2025` | rider |

## Layout

Mobile layouts below 760 px, two-column (map beside a scrolling sheet) above,
fluid type and padding via `cl(...)`, safe-area aware, system font scale capped at
120 %. Motion tokens live in `lib/core/motion.dart` (`Motion.soft` easing, 140–560 ms
durations) and are used through `PageSwap`, `Entrance`, `Pressable`, `CountUp`,
`AnimatedProgress` and `PulseDot` in `lib/core/widgets.dart`.