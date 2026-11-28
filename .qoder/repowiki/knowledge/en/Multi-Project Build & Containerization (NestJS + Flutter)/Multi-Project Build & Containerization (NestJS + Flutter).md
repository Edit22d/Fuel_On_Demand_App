---
kind: build_system
name: Multi-Project Build & Containerization (NestJS + Flutter)
category: build_system
scope:
    - '**'
source_files:
    - backend/package.json
    - backend/nest-cli.json
    - backend/tsconfig.build.json
    - backend/Dockerfile
    - backend/.env.example
    - flutter_app/pubspec.yaml
    - flutter_app/analysis_options.yaml
    - flutter_app/serve_web.js
---

## Overview

FuelConnect is a monorepo with two independently built targets:

- **Backend** (`backend/`): NestJS application compiled from TypeScript to Node.js, containerized via Docker.
- **Frontend** (`flutter_app/`): Flutter app targeting Android/iOS/web, built through the Flutter toolchain.

There is no top-level Makefile or CI pipeline in this repository; each subproject owns its own build configuration. The root only contains shared assets (screenshots, README).

## Backend Build System

### Toolchain

- **Compiler**: TypeScript 5.7.3, invoked by `@nestjs/cli` (`nest build`).
- **Build config**: `tsconfig.build.json` extends `tsconfig.json` and excludes `test`, `dist`, `**/*spec.ts`, and `prisma/seed.ts` from the production build.
- **Nest CLI**: `nest-cli.json` declares `sourceRoot: src` and sets `compilerOptions.deleteOutDir: true` so `npm run build` cleans `dist/` before emitting.
- **Prisma codegen**: `postinstall` hook runs `prisma generate`; scripts `prisma:generate`, `prisma:push`, `prisma:migrate`, `prisma:studio`, and `db:seed` are provided.
- **Node engine constraint**: `package.json` pins `engines.node >= 20.0.0`.

### Scripts (`backend/package.json`)

| Script | Purpose |
|---|---|
| `build` | `nest build` — compiles TS → `dist/` |
| `start` | `nest start` (dev) |
| `start:dev` | `nest start --watch` |
| `start:debug` | `nest start --debug --watch` |
| `start:prod` | `node dist/main` |
| `typecheck` | `tsc --noEmit` |
| `db:setup` | `prisma generate && prisma db push && npm run db:seed` |
| `postinstall` | `prisma generate` |

### Docker Image (`backend/Dockerfile`)

Two-stage build using `node:22-alpine`:

1. **builder stage**: installs `openssl`, copies `package*.json` + `prisma/`, runs `npm ci`, then copies source and `tsconfig*.json` / `nest-cli.json` and runs `npm run build`.
2. **runner stage**: fresh `node:22-alpine` image, installs `openssl`, runs `npm ci --omit=dev && npm cache clean --force`, copies `dist/` from builder, copies `public/`, exposes port `8000`, and starts `node dist/main`.

The runtime image does not include dev dependencies or TypeScript sources — only the compiled `dist/` tree plus Prisma schema/assets.

### Environment

- `.env.example` provides the template; `.env` holds local values.
- Configuration is loaded via `@nestjs/config` with validation in `src/config/env.validation.ts`.

## Frontend Build System

### Toolchain

- **SDK constraints** (`pubspec.yaml`): Dart SDK `>=3.4.0 <4.0.0`, Flutter `>=3.24.0`.
- **Versioning**: `version: 1.0.0+1` (semantic version + build number).
- **Publishing**: `publish_to: 'none'` — the app is not published to pub.dev.
- **Assets**: images under `assets/images/` are bundled via the `flutter:` section of `pubspec.yaml`.
- **Linting**: `flutter_lints ^4.0.0` as a dev dependency; `analysis_options.yaml` is present at the project root.
- **Web helper**: `serve_web.js` is included for serving the web target locally.

No custom Gradle or Xcode build scripts are authored beyond the Flutter-generated defaults under `android/` and `ios/`.

## Conventions Observed

- Each subproject is self-contained: backend uses `package.json` + Nest CLI + Prisma; frontend uses `pubspec.yaml` + Flutter toolchain.
- Production builds exclude test files and seed data (`tsconfig.build.json` explicitly excludes `**/*spec.ts` and `prisma/seed.ts`).
- Docker uses a multi-stage Alpine-based image with `npm ci` (not `npm install`) for reproducible installs.
- Dev-only dependencies are stripped from the runtime image via `--omit=dev` and `npm cache clean --force`.
- The backend's `postinstall` hook ensures Prisma client generation happens automatically after `npm install`.
- No top-level orchestration script exists: there is no Makefile, no shell wrapper that builds both targets together, and no CI configuration file (e.g., GitHub Actions, GitLab CI) in the repository.
- Version numbers live in the language-native manifests (`package.json` for backend, `pubspec.yaml` for frontend); they are not synchronized by a central script.