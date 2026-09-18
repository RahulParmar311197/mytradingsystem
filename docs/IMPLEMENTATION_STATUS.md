# Implementation status

Updated: 2026-09-18. This is an honest Phase 0–3 status, not a production-readiness claim.

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
- The first Phase 3 slice implements deterministic SMA, EMA, RSI, MACD, ATR, ADX, Bollinger Bands, cumulative
  VWAP, Supertrend, ROC, stochastic oscillator, volume averages/relative volume, confirmed pivots,
  support/resistance, and gap detection. Outputs have explicit `None` warm-up values, reject non-finite input,
  remain index-aligned, and do not read future observations.
- The second Phase 3 slice implements versioned confirmed swings, close-confirmed BOS/CHOCH, wick-rejection
  liquidity sweeps, three-candle fair-value gaps, evidence timestamps, confidence/invalidation explanations,
  and frontend-neutral overlay records. It accepts closed, ordered, single-stream candles only and never treats
  an FVG or structural label as evidence of institutional intent.
- Fair-value gaps now have point-in-time active, mitigated, and invalidated states, first transition timestamps,
  consequent encroachment, and close-through inverse FVGs. Wick invalidation is deliberately distinct from
  close-confirmed inversion, and overlays extend only through the analysis snapshot or invalidation time.
- Displacement uses a configurable prior-body baseline and directional close-location threshold. Consecutive
  confirmed swings within a configurable percentage form buy-side/sell-side equal-level bands. MSS is distinct
  from CHOCH and requires a same-candle displacement, retaining the combined causal evidence set.
- Asia/Kolkata previous-day/week and evolving current-session levels, confirmed dealing-range premium/discount
  and directional 62%–79% OTE zones, and explicit fixed-IST kill-zone windows are available with evidence and
  availability times. All analytical event times now represent candle close rather than interval start.
- Displacement-confirmed structure breaks now create order blocks from the latest opposing candle inside a
  finite lookback. First retests emit mitigation blocks; directional close-through invalidation emits an
  opposite breaker block. Each transition retains its causal origin and evidence timestamps.
- Internal and external swings use separately configurable confirmation windows and independently scoped
  BOS/CHOCH/MSS streams. Only external structure can create price blocks. Phase 3 deterministic backend rules
  and neutral overlay contracts are complete; actual browser chart rendering remains Phase 11 frontend work.
- The first Phase 4 slice provides a transparent point-in-time regime classifier with independent bull/bear/range,
  high/normal/low volatility, high/normal/low liquidity, and event-risk axes. Results include bounded explanatory
  confidence, supporting features, UTC timestamp, rule version, and an explicit event-risk entry lock.
- Five versioned deterministic strategies now share one validated context/result contract: trend continuation,
  liquidity-sweep reversal, opening-range breakout, FVG continuation, and range-only mean reversion. Each declares
  timeframes/features/regimes, applies common safety gates, treats NO_TRADE as normal, and returns only proposed
  levels plus a capped risk-fraction request—not an order or final quantity.
- The explainable decision engine combines bounded technical, SMC/ICT, regime, volume, options, optional ML,
  data-quality, and descriptive risk-context scores with validated weights. It rejects weak confidence, bad data,
  invalid price geometry, and insufficient risk/reward to NO_TRADE; entry results explicitly require independent
  risk approval. Missing ML is excluded and remaining weights are renormalized.
- The first Phase 5 slice is an event-driven, long/short next-candle market backtester consuming actual decision
  results. It prevents same-candle fills, gives stops conservative priority over targets, models adverse slippage
  and two-sided costs, revalidates gap-fill geometry, records risk-policy rejection, marks entry cost immediately,
  and produces a trade ledger, equity/drawdown curves, and core performance metrics.
- Phase 5 robustness utilities provide non-shuffled train/validation/test splits, expanding or rolling walk-forward
  folds, seeded Monte Carlo trade-sequence risk, neighbor-aware parameter stability, turnover-based incremental
  cost sensitivity, and aligned benchmark comparison. Monte Carlo is explicitly limited to sequence risk.

## Missing capabilities and technical debt

The advanced Phase 5 execution models and robustness analysis, actual frontend chart rendering, and Phases 6–12
are not implemented.
Live ticks, quotes, depth,
WebSocket reconnect/resubscribe, corporate-action
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
four-hour session-close behavior, and weekly point-in-time availability. On 2026-09-18 the existing baseline
was rerun after installing declared development extras: 19 tests passed. The indicator and initial SMC/ICT
slices raise the suite to 66 passing tests with hand-calculated reference fixtures, warm-up, causal confirmation,
closed-candle validation, evidence tracking, wick-versus-close structure checks, and prefix-based FVG lifecycle
tests proving future candles do not alter earlier snapshots. Displacement, delayed equal-level availability, and
CHOCH-versus-MSS strength are independently tested.
Indian calendar grouping, confirmed dealing-range geometry, half-open/overnight kill zones, and close-time
availability semantics are independently tested.
Order-block origin selection and prefix snapshots covering active, mitigated, invalidated, and breaker states
are independently tested.
Independent internal/external confirmation and structure streams, scoped overlays, and the external-only block
boundary are independently tested.
Regime-axis classification, evidence, confidence bounds, event-risk locking, and invalid input/configuration are
independently tested.
All five strategies, their required confirmations, optional ORB retest, range restriction, proposed levels, sizing
request, and shared event/session NO_TRADE gates are independently tested.
Decision weighting, optional-ML fallback, data-quality/confidence rejection, directional price geometry,
risk/reward, NO_TRADE propagation, and EXIT/HOLD preservation are independently tested.
Backtests prove next-candle entry/exit timing, conservative ambiguous-bar stops, costed target fills, risk-policy
rejection, invalid gap geometry rejection, and prefix-only decision-provider access.
Chronological partitions, rolling/expanding folds, seeded Monte Carlo reproducibility, isolated-optimum rejection,
incremental cost sensitivity, and aligned benchmark excess return are independently tested.

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
