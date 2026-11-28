---
kind: external_dependency
name: PostgreSQL 16 + PostGIS 3.4 (Prisma)
slug: postgresql-postgis
category: external_dependency
category_hints:
    - client_constraint
scope:
    - '**'
---

### Identity
PostgreSQL 16 with the `postgis` extension (via Prisma 6 `postgresqlExtensions` preview feature) is the sole relational store.

### Role in this repo
- Distance / ETA / nearest-rider dispatch uses raw PostGIS functions (`ST_DWithin`, `ST_Distance`) against `stations.location` and customer addresses.

### Integration notes
- Docker Compose spins `postgis/postgis:16-3.4`; without Docker a local PG 16 instance with the `postgis` extension is required.
- In dev the API connects to `localhost:5432` from `.env`; leftover `DATABASE_URL` env vars pointing at other ports (e.g. `:5999`) will cause `P1001` startup failures — always clear inherited DB variables before launching.
- The seed script creates demo stations, accounts and one completed order so admin screens have data on first run.