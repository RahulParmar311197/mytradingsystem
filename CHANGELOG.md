# Changelog

## Unreleased

- Audit the initially empty repository and document architecture/status/roadmap.
- Add Phase 1 configuration safety interlocks, typed domain contracts, persistence/migration, observability,
  health API, development containers, CI gates, and tests.
- Add the Phase 2 historical-data slice: provider contracts, instrument/raw/normalized persistence,
  idempotent ingestion, visible quality events, and point-in-time NSE-aligned candle aggregation.

## 2026-09-17 - Foundation verification

Re-audited existing main, hardened domain/configuration/logging/readiness, persisted audited safety
controls and worker health, corrected Compose privileges and migration startup, locked dependencies,
and added recovery/security/PostgreSQL CI checks. Live execution remains unavailable.
