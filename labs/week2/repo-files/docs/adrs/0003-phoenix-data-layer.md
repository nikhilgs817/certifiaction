# ADR-0003: Phoenix data layer — official TimescaleDB and Redis images as StatefulSets

- **Status:** Accepted · **Date:** 2026-11-16

## Context
Phoenix needs PostgreSQL (SQLAlchemy + Alembic; the plan calls for TimescaleDB for bar data in L8) and Redis
(planned for the L2 agents). Single node, local-path storage, around-the-clock uptime, free and maintained images.
Bitnami moved its versioned images to the unmaintained `bitnamilegacy` repository in Aug–Sep 2025, leaving only a
small free "latest" set, so Bitnami charts are no longer a pinned, maintained option.

## Decision
- **TimescaleDB 2.31.0 on PostgreSQL 18** (official `timescale/timescaledb`, pinned by digest) as a 1-replica
  StatefulSet, PVC on `local-path-retain`, non-root (uid 70), read-only root filesystem.
- **Redis 8.10.3** (official `redis:alpine`, pinned by digest) as a 1-replica StatefulSet with AOF persistence.
- App credentials keep the CNPG contract: Secret `phoenix-db-app` with key `uri`, so a later move to CloudNativePG
  needs no app change.
- Backups: nightly `pg_dump -Fc` CronJob to a Retain PVC; restore test in the runbook.

## Alternatives
| Option | Why not now |
|---|---|
| CloudNativePG 1.30 + TimescaleDB | Best for HA and PITR, but TimescaleDB on CNPG needs a custom image. Revisit on AWS |
| Bitnami charts | Versioned images unmaintained since 2025 (see Context) |
| Valkey 9.1 instead of Redis | Drop-in and BSD-licensed; a good swap later. Redis 8 is fine for personal use (AGPLv3 option since 8.0) |

## Consequences
- Plain manifests teach StatefulSets, headless Services and PVC templates (CKA).
- No automatic failover: a node or disk loss means a restore from backup.
