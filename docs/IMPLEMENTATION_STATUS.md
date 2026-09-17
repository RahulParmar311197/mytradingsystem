# Implementation status

Updated: 2026-09-17. This is an implementation record, not a production-readiness claim.

## Re-audit of existing main (this implementation)

Starting commit: `0ef132c5fd802376a7000887b1395ca5af9a3f2d`. The checkout is clean; no
AGENTS.md exists. The complete tree contains 44 files with working Phase 1/2 slices,
not an empty project. Existing work is preserved on `codex/verified-platform-foundation`.
The older audit below describes the earlier initialization and is retained as history.

Actual baseline: Ruff format (35 files), Ruff lint, strict MyPy (20 source files),
Bandit, and all 19 Pytest tests pass. Two third-party deprecation warnings occur.
Offline PostgreSQL migration SQL generation succeeds. Local Docker build exits 127
because Docker is unavailable; upstream CI run 35179976121 passed both existing jobs.

Audit findings to repair before expansion:

- JSON date strings bypass the before-validator's timezone check.
- Readiness tests only connectivity, not schema revision or Redis.
- Live configuration flags are assertions, not verified runtime safety evidence.
- Secret redaction misses nested objects, interpolated messages, and URL passwords.
- HTTP metrics label arbitrary paths, permitting unbounded cardinality.
- Docker uses host-local DB/Redis URLs inside containers, does not run migrations,
  exposes data services publicly, and grants the application a superuser role.
- Aggregation accepts mixed instruments, misaligned inputs, and invalid weekly sets.
- Open normalized candles can become permanently frozen by insert-ignore ingestion.
- There is no runnable historical-data API, authentication, worker, or web application.
- No production broker, ML, strategy, risk evaluation, or execution code exists.

The only `pass` occurrences are Alembic generation templates. Protocol ellipses and
the health-test fake are intentional boundaries/test doubles. No real credentials
were found; `change_me` is an unsafe development default to remove from deployment.

Next: harden and validate the foundation, complete the historical-data vertical
slice, then implement deterministic analysis. Every later phase remains incomplete
until its actual verification evidence is recorded.

## Audit and baseline

The repository contained only `.gitkeep` and one initialization commit. It had no application, README,
configuration, tests, formatter/linter/type-check/build commands, credentials, placeholders, dangerous live
defaults, or unrelated user changes. Consequently no pre-change quality command existed to run. Python 3.12,
Node 20, pytest, Ruff and MyPy were present; application dependencies were absent.

## Existing capabilities

- Immutable provider-independent domain contracts cover the requested Phase 1 entities, reject naive
  timestamps, normalize aware timestamps to UTC, use `Decimal` for precision, and validate OHLC/spreads.
- Environment settings default to paper. Live mode fails validation unless all ten safety conditions pass,
  including exact explicit confirmation. This validates configuration only; it is not live authorization.
- Async SQLAlchemy foundation and initial Alembic migration persist accounts, risk limits, audit events and
  kill/safety state. The API provides liveness, database-aware readiness, metrics, correlation IDs, baseline
  secure headers, an explicit mode field, JSON logging and secret-field redaction.
- Local PostgreSQL/Redis Compose services, non-root/read-only API image, and initial CI quality gates exist.
- The Phase 2 historical-data slice defines provider-independent instrument/history contracts, persists raw
  payloads separately from normalized candles, records quality failures without silently repairing them, and
  makes ingestion idempotent under PostgreSQL and SQLite conflict semantics. NSE-session-aligned aggregation
  supports 3m, 5m, 15m, 30m, 1h, 4h, daily, and weekly targets and emits only complete point-in-time buckets.

## Missing capabilities and technical debt

Phases 3–12 are not implemented. Live ticks, quotes, depth, WebSocket reconnect/resubscribe, corporate-action
adjustment, exchange-holiday-aware weekly aggregation, and external provider adapters remain Phase 2 follow-up.
There is also no authentication/RBAC, strategy, backtester, paper/live execution, complete risk engine, broker
integration, frontend, worker,
tracing, TimescaleDB tuning, Redis health gate, backups, alerting, or broker/regulatory validation. API rate
limiting and durable audit emission are also pending. Broad domain contracts precede their repositories and
services. Dependency/container vulnerability audit and a real PostgreSQL migration round trip remain required.

## Test status

Baseline: no tests or build existed. Phase 1 verification covers default-off/live interlocks, UTC/Decimal and
market validation, secret redaction, liveness/security headers, and fail-closed database readiness. Phase 1
ended with 9 passing Pytest tests (two upstream deprecation warnings), clean Ruff format/lint, strict MyPy,
Bandit, and successful offline PostgreSQL migration generation. The API was also started against SQLite and
both health endpoints returned ready in paper mode. Docker validation was unavailable because this environment
does not contain the Docker executable; CI retains the container-build gate.
Phase 2 finishes with 19 passing tests, including SQLite ingestion persistence/idempotency and hand-built
fixtures proving NSE boundaries, incomplete-bucket suppression, session filtering, daily completeness,
four-hour session-close behavior, and weekly point-in-time availability.

## Blockers

No credential blocks Phase 2. Broker credentials and owner compliance decisions will be required only for
opt-in live tests/release. Regulatory assumptions must be researched against current primary sources before
broker execution is designed.

## Definition of done

Each phase requires executable vertical behavior, migrations where relevant, deterministic tests, format,
lint, strict typing, security checks, runnable affected services, and updated docs. Platform production
readiness additionally requires the complete acceptance demonstration, sandbox contracts, restart recovery,
reconciliation, monitoring/alerts, tested backups, security gates, operational runbooks, and explicit owner
authorization. Profitability and regulatory approval are separate from software correctness.

## Foundation repairs implemented in this branch

- Parsed UTC timestamp validation, finite Decimal validation, required order prices, and fill bounds.
- Schema-aware readiness; bounded Redis checks; explicit refusal of unavailable live execution.
- Recursive redaction, correlation contexts, template-based metrics, latency metrics, optional OTLP spans.
- Migration 0003 initializes a fail-closed kill switch and persists worker heartbeats. SQLite defaults
  in migrations 0001/0002 now use SQLAlchemy's dialect-aware `now()` (same PostgreSQL semantics).
- Local operator CLI, transactional audit/safety updates, recovery tests, real operational worker.
- Correct container service URLs, separate migration job, non-superuser app DB role, private bindings,
  generated local credentials, locked/hashes dependencies, Prometheus rules, and expanded CI gates.
- Security/threat-model/operational docs. These are foundation controls, not a complete risk engine.

Local verification after repairs: 36 tests passed, plus a dedicated PostgreSQL test added for CI;
Ruff, strict MyPy, and Bandit pass. SQLite clean migrations, actual worker `--once`, and operator
safety inspection succeed. PostgreSQL installation was blocked by local package-manager privilege
restrictions; Docker is absent. Current-branch CI results will be recorded separately.
