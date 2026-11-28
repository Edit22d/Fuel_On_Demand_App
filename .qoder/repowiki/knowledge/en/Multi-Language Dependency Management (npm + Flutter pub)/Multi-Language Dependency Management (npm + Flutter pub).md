---
kind: dependency_management
name: Multi-Language Dependency Management (npm + Flutter pub)
category: dependency_management
scope:
    - '**'
source_files:
    - backend/package.json
    - backend/package-lock.json
    - flutter_app/pubspec.yaml
    - flutter_app/pubspec.lock
---

## Overview

FuelConnect is a monorepo with two independently managed language stacks, each using its native package manager:

- **Backend** (`backend/`): Node.js / NestJS — dependencies declared in `package.json`, resolved via npm and pinned by `package-lock.json`. A `.gitignore` excludes `node_modules/`.
- **Flutter Frontend** (`flutter_app/`): Dart/Flutter — dependencies declared in `pubspec.yaml`, resolved via `flutter pub` and pinned by `pubspec.lock`. The `.dart_tool/` directory is gitignored.

There is no cross-language dependency orchestrator (no Lerna, pnpm workspaces, Turborepo, etc.); each subproject manages its own dependency graph.

## Backend (npm)

- Manifest: `backend/package.json`
- Lockfile: `backend/package-lock.json` (committed to the repo, ensuring deterministic installs).
- Node engine constraint: `"engines": { "node": ">=20.0.0" }`.
- Runtime dependencies include NestJS core packages (`@nestjs/*` v11), Prisma client (`@prisma/client` 6.16.2), Socket.IO, Redis adapter, JWT/passport auth, Helmet, Joi/class-validator for input validation, and ioredis.
- Dev dependencies include the Nest CLI, TypeScript (^5.7.3), ts-node, tsconfig-paths, and Prisma CLI (version-aligned with the runtime client at 6.16.2).
- Postinstall hook: `"postinstall": "prisma generate"` runs `prisma generate` automatically after `npm install`, keeping generated Prisma types in sync with `prisma/schema.prisma`.
- Scripts expose `prisma:generate`, `prisma:push`, `prisma:migrate`, `prisma:studio`, and `db:seed`/`db:setup` for database bootstrapping.
- No private registry or `npmrc` configuration is present; packages are sourced from the public npm registry.

## Flutter Frontend (pub.dev)

- Manifest: `flutter_app/pubspec.yaml`
- Lockfile: `flutter_app/pubspec.lock` (committed, pinning transitive resolution).
- SDK constraints: `sdk: '>=3.4.0 <4.0.0'` and `flutter: '>=3.24.0'`.
- Dependencies are minimal: `flutter_svg`, `flutter_secure_storage`, `google_fonts`, `shared_preferences`, `crypto`, `url_launcher` — all pulled from pub.dev with caret (`^`) version ranges.
- Dev dependencies: `flutter_test` (from SDK) and `flutter_lints ^4.0.0` for linting rules consumed via `analysis_options.yaml`.
- `publish_to: 'none'` declares the app as not publishable to pub.dev.
- No custom pub repository overrides or private registries are configured.

## Conventions Observed

- Each subproject pins exact versions for critical tooling (e.g., `@prisma/client` and `prisma` both at `6.16.2`; NestJS ecosystem all on `^11.x`).
- Lockfiles are committed alongside manifests, so CI and local installs resolve deterministically without re-resolving transitive dependencies.
- Version ranges use npm's caret (`^`) and pub.dev's caret semantics, allowing patch-level updates while locking major versions.
- The backend uses a `postinstall` script to keep Prisma-generated code in sync — this is an enforced build-time convention rather than a developer choice.
- There is no vendoring of third-party source code; all packages are fetched at install time from their respective public registries.