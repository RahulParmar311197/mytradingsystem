# Implementation status

Updated: 2026-09-25. Historical phase notes below are retained; this PR contains additional partial slices and is not production ready.

## Current integration state

PR #3 has been combined locally with the Phase 5 extensions on `main` (pluggable Indian charge model, reports and out-of-sample selection). On the combined tree, 224 tests pass. Contract tests inject a test execution authorizer; default Upstox and Dhan adapters refuse order dispatch. This is a temporary fail-closed boundary, not a production live authorization implementation. Risk rejects an exit whose side would increase a position, evaluates gross/net/sector/strategy limits against the proposed order, and treats a SUBMITTING order without a broker ID as unresolved.

Outstanding before live authorization: persistent proof of risk and kill-switch state at dispatch, authenticated broker connectivity, database and market-data health checks, verified position reconciliation, compliance review and production migrations against PostgreSQL. This is neither a production readiness nor a strategy profitability claim.

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
- A pluggable effective-dated India charge model itemizes capped/percentage brokerage, exchange, SEBI, IPFT, GST,
  side-specific STT, and buy-side stamp duty. No unverified statutory defaults are committed: official-source
  lookup was unavailable during implementation, so owner-verified schedules remain a documented blocker.
- Immutable performance reports add Asia/Kolkata daily/monthly returns, downside Sortino, explicitly linearized
  Calmar, elapsed-time exposure, and long/short trade breakdowns without assigning a success label.
- Out-of-sample selection exposes only train/validation partitions during candidate scoring and invokes the held-out
  evaluator exactly once after deterministic selection, retaining all validation scores in its result.
- The first Phase 6 slice persistently executes risk-approved paper market orders with adverse slippage, pluggable
  costs, restart-safe idempotency, fills, long/short position accounting, realized P&L, and lifecycle events.
- Paper cash ledgers now account for fill notionals and charges. Point-in-time portfolio marks persist realized and
  unrealized P&L, equity, gross/net exposure, peak-equity drawdown, and per-position pricing evidence.
- The first Phase 7 slice independently rejects locked/unsafe entries, enforces quote freshness/spread, daily-loss
  and open-position limits, resizes by stop risk and instrument exposure, and preserves bounded exits during locks.
- Final risk decisions are persisted once per order intent with policy/reason evidence and an input fingerprint;
  identical restart retries return the original decision while changed-input reuse fails closed.
- Effective-dated persisted limits load latest-as-of without future leakage and fail closed when incomplete. Manual
  kill-switch state persists across restart and every change records actor, reason, correlation ID, and audit event.
- New-entry risk locks now include weekly loss, portfolio drawdown, gross/net exposure, order-rate throttling, and a
  consecutive-loss circuit breaker; all remain bypassed only by position-bounded exit intents.
- Sector and strategy allocation, expected slippage, and explicit cooldown locks are enforced. Severe loss,
  drawdown, or consecutive-loss breaches can activate the durable kill switch with an automatic audit record.
- The first Phase 8 slice implements an idempotent order-state reducer covering risk approval, submission,
  acknowledgement, partial/full fills, cancellation, rejection, expiry, and mandatory reconciliation after an
  unknown submission outcome. Conflicting, overfill, and out-of-order evidence fails closed.
- Execution order state and immutable source events are persisted with optimistic version checks. Restart
  reconstruction retains fills, broker identity, processed event IDs, and reason-coded reconciliation state.
- Broker/local order reconciliation detects unknown, missing, duplicate, quantity/fill, and status discrepancies.
  Any discrepancy makes the result unsafe for new trading; reconciliation never silently rewrites local truth.
  Independent risk consumes reconciliation health as a fail-closed new-entry lock without suppressing bounded exits.
- Upstox and Dhan v2 order adapters map place/details/cancel requests to documented endpoints. Placement requires a
  matching approved risk decision, supplies client correlation identity, and is never retried automatically.
- The first Phase 9 slice provides Black–Scholes call/put price and Greeks, bounded implied-volatility solving,
  OI-based PCR/max pain, strict chain-identity validation, multi-factor liquidity gating, and multi-leg expiry payoff.
- Signed lot-aware option positions aggregate gross marked exposure and portfolio Greeks; the independent risk engine
  applies persisted projected exposure, absolute delta, and absolute gamma ceilings before approving a new entry.
- Point-in-time IV percentile rejects future/duplicate/undersized history; broker Greek comparison is freshness- and
  tolerance-aware; deterministic delta selection requires both liquid quotes and fresh Greek evidence.
- Option IV history is stored idempotently by provider event identity and queried with a database-enforced as-of
  cutoff, preserving chronological restart-safe inputs for percentile calculation.
- Cross-expiry selection uses the India-market date, explicit inclusive DTE bounds, configurable nearest/farthest
  preference, and the same quote/Greek liquidity controls applied to single-chain delta selection.
- A versioned research-only option margin estimate exposes premium outlay, every configured spot-shock loss, maximum
  scenario loss, and a short-notional floor; it is explicitly not an authoritative broker margin substitute.
- Normalized option-chain snapshots are identity-validated and stored with provider idempotency; latest-as-of queries
  reconstruct strict domain chains across restarts without exposing later snapshots.
- Original option-chain provider payloads are retained separately from normalized snapshots; retries compare both
  representations and orphaned raw/normalized events fail closed instead of being silently repaired.
- Phase 10 starts with a deterministic scikit-learn logistic baseline using versioned exact feature schemas,
  availability timestamps, chronological train/validation cutoffs, leakage guards, and multi-metric evaluation.
- The baseline reports calibration error and versioned coefficient importance; point-in-time PSI drift rejects future
  observations and exact-schema mismatches. Neither output has decision, risk, or execution authority.
- A metadata-only model registry persists checksummed artifact references and challenger/champion/archive stages
  without deserializing binaries; prediction logs fingerprint complete point-in-time evidence and are idempotent.
- Side-effect-free champion comparison requires compatible model families/features, finite complete metrics, minimum
  primary improvement, and bounded named guardrail regressions; it cannot promote a model automatically.
- Optional Platt calibration uses disjoint chronological train/calibration/validation windows with two-class guards;
  calibrated predictions retain the same availability-time, schema, model-version, and non-authority boundaries.
- A bounded random-forest challenger uses explicit depth/leaf/tree/seed controls, one worker, the same chronological
  leakage guards and metrics, and versioned impurity-importance evidence; it remains scoring-only.
- A bounded gradient-boosting challenger fixes tree count, learning rate, depth, leaf size, and seed while preserving
  the same chronological leakage guards, multi-metric validation, versioned importance, and scoring-only boundary.
- Local ML artifacts are stored as opaque content-addressed bytes with atomic no-overwrite publication, size/checksum
  verification, root containment, and symlink rejection; the store never deserializes model content.
- A vendor-neutral remote artifact boundary uses an injected conditional-create/get client, configured bucket/prefix,
  digest-derived keys, strict evidence URIs, and size/checksum verification without owning credentials or transport.
- A thin S3 adapter accepts an externally configured SDK client, conditionally creates immutable objects, distinguishes
  precondition conflicts from operational failures, and bounds and closes response streams during retrieval.
- A metadata-only MLflow exporter accepts an externally configured client and logs validated identities, finite
  metrics, artifact evidence, and explicit non-authority tags without uploading bytes or promoting registry stages.
- Phase 11 starts with secret-backed opaque bearer authentication, constant-time digest comparison, viewer/operator
  RBAC, fail-closed unconfigured behavior, and read-only authenticated session/mode endpoints.
- A bounded rotation grace accepts separately configured previous viewer/operator tokens only before one aware expiry;
  short, duplicate, expiry-free, naive-expiry, and expired previous credentials fail closed.
- Configuration-driven immediate revocation accepts only unique lowercase SHA-256 digests, compares them in constant
  time, overrides current and grace-token matches, and never requires storing revoked plaintext tokens.
- API token revocation evidence can be persisted idempotently with UTC effective time, actor, and reason; conflicting
  digest reuse fails closed and as-of queries exclude future-effective revocations across session restarts.
- Protected API requests can opt into a fresh persistent revocation lookup using the internal credential digest;
  effective revocations return generic unauthorized responses and any lookup/schema failure denies access with 503.
- An operator-only API atomically persists revocation and audit records using authenticated actor and correlation
  evidence; identical retries are idempotent, viewers are forbidden, and conflicting reuse fails closed.
- The first replay slice emits a single closed-candle stream strictly at interval-close availability, exposes only the
  replayed prefix, supports aware-time forward/backward seek, and restores dataset-bound deterministic checkpoints.
- Replay sessions persist stream identity, cursor, total events, checkpoint time, and optimistic version; idempotent
  creation requires identical evidence and stale, mismatched, or out-of-range checkpoint writes fail closed.
- Replay coordination reloads immutable candle evidence for every step, seek, or snapshot, verifies all persisted stream
  identity before restoring, and combines expected-version mutation with atomic checkpoint persistence.
- Logistic inference can be reconstructed from a strict versioned canonical-JSON format that validates finite,
  schema-aligned scaler and linear-model parameters without loading an executable Python object graph.

## Missing capabilities and technical debt

The remaining advanced Phase 5 work, incomplete Phase 6–8 capabilities, actual frontend chart rendering, and
Phases 9–12 remain incomplete.
Live ticks, quotes, depth,
WebSocket reconnect/resubscribe, corporate-action
adjustment, exchange-holiday-aware weekly aggregation, and external provider adapters remain Phase 2 follow-up.
There is also no authentication/RBAC, live execution, complete risk engine or broker integration, frontend, worker,
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
was rerun after installing declared development extras: 19 tests passed. The current suite has 205 passing tests,
including hand-calculated indicator references, warm-up behavior, causal confirmation,
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
India charge component formulas, asymmetric sides, caps, invalid-rate rejection, and entry/exit cost-model wiring
are independently tested with synthetic—not statutory—rates.
IST report boundaries, period compounding, direction aggregation, exposure, Sortino/Calmar availability, and
configuration rejection are independently tested.
Out-of-sample tests prove the held-out partition is absent from scoring, only the selected candidate is tested,
ties are stable by configured order, and empty/non-finite inputs fail closed.
Paper-broker integration tests prove rejected/mismatched risk decisions cannot create orders, risk resizing controls
fill quantity, persisted idempotency survives a new broker/session, and duplicate requests do not duplicate fills,
events, or positions. The same integration path verifies persisted cash, unrealized P&L, equity, and exposure.
Risk-engine tests cover every implemented entry lock, deterministic resize, reason codes, and the invariant that a
kill switch blocks new exposure without preventing a position-bounded exit.
Risk persistence integration verifies restart recovery, single-record idempotency, and rejection of changed inputs
for an intent that already has a final decision.
Risk-configuration integration verifies latest-effective limit selection, future-limit exclusion, derived policy
versions, kill-switch restart recovery/audit emission, and missing-configuration failure.
Risk unit fixtures independently exercise weekly-loss, drawdown, gross/net exposure, order-rate, and consecutive-loss
entry locks in addition to the original operational controls.
Sector/strategy allocation, slippage, and cooldown locks are independently tested; integration covers both no-op
safe automatic-kill evaluation and audited activation on a configured drawdown boundary.
Order lifecycle fixtures prove duplicate callback idempotency, cumulative partial fills, cancellation after partial
fill, overfill/conflicting-ID/out-of-order rejection, and the prohibition on resubmitting an unknown outcome.
Execution-repository integration proves state/event recovery after a new session, persisted callback idempotency,
partial-fill reconstruction, and durable unknown-submission reconciliation reasons.
Reconciliation fixtures prove exact matches are safe, pre-broker states are excluded, and every unknown, missing,
duplicate, fill/quantity, or status discrepancy locks new trading with a typed issue.
Mock-transport broker contracts verify Upstox/Dhan endpoint, authentication, correlation, instrument and order field
mappings, no retry on placement failure, and rejection before network I/O when risk approval does not match.
Options fixtures validate Black–Scholes prices/Greeks against reference values, IV round-trip tolerance, PCR, max
pain, volume/OI/spread/depth/freshness filtering, payoff curves, and fail-closed invalid model inputs.
Portfolio fixtures verify signed contract-multiplier Greek aggregation and projected exposure/delta/gamma rejections.
Additional fixtures prove future IV observations are excluded, stale broker Greeks fail closed, tolerance differences
are visible, and delta selection cannot bypass quote/Greek freshness and liquidity requirements.
SQLite integration proves IV ingest idempotency, conflicting-event rejection, restart recovery, and as-of exclusion.
Expiry fixtures verify India-date DTE filtering, explicit near/far preference, and future-snapshot rejection.
Margin fixtures verify long-premium, short-loss, notional-floor, scenario evidence, and configuration validation.
SQLite integration proves paired raw/normalized chain idempotency, conflict rejection, restart recovery, and
latest-as-of behavior.
ML fixtures verify chronological splitting, two-class/labeled training requirements, exact feature schemas,
availability-time prediction guards, deterministic scoring, and Brier/log-loss reporting.
ML monitoring fixtures verify calibration-error bounds, normalized coefficient shares, shifted/stable PSI behavior,
and future-observation rejection.
ML registry integration verifies restart recovery, single-champion promotion, prior-champion archival, identical-log
idempotency, and rejection when a prediction ID is reused with different evidence.
Champion/challenger fixtures verify primary thresholds, guardrail rejection, feature-version compatibility, missing
evidence rejection, and accepted reason codes without registry side effects.
Calibration fixtures verify three-window isolation, two-class requirements, bounded probabilities, validation metrics,
version retention, and future-feature rejection.
Random-forest fixtures verify repeated-run determinism, chronological validation, normalized versioned importance,
bounded probabilities, configuration validation, and future-feature rejection.
Gradient-boosting fixtures verify repeated-run determinism, chronological validation, normalized versioned importance,
bounded probabilities, configuration validation, and future-feature rejection.
Artifact security fixtures verify content addressing, identical-write idempotency, tamper detection, size limits,
root-escape and symlink rejection, and byte-only handling of pickle-like content.
Remote-artifact fixtures verify conditional-create idempotency, digest-derived identity, conflict/tamper detection,
configuration validation, URI containment, query rejection, and checksum-evidence validation.
S3 adapter contract fixtures verify conditional request mapping, credential omission, narrow precondition handling,
bounded reads, content-length enforcement, malformed-body rejection, and stream closure.
MLflow contract fixtures verify metadata/metric mapping, non-authority tags, run identity, context closure, and
rejection of naive timestamps, missing identity, empty/non-finite metrics, and invalid artifact evidence.
Authentication fixtures verify token format and configuration validation, viewer/operator hierarchy, invalid-token
rejection, Bearer challenges, fail-closed missing configuration, and read-only protected API responses.
Rotation fixtures verify the explicit previous-token window, aware-expiry requirement, expiry-bound rejection, and API
acceptance only during the configured grace period.
Revocation fixtures verify strict digest validation, rejection of current and previous credentials, role isolation,
and protected API denial without disabling unrelated configured credentials.
Revocation-persistence integration verifies restart recovery, identical retry idempotency, conflicting-evidence
rejection, UTC normalization, and point-in-time exclusion before the effective revocation timestamp.
Protected-API integration verifies persistent revocation is checked on every request, unrelated roles remain usable,
revoked digests are not returned, and missing revocation schema/infrastructure fails closed.
Operator-workflow integration verifies viewer denial, authenticated actor/correlation evidence, atomic audit creation,
retry idempotency, and immediate request-time enforcement after a successful revocation.
Replay fixtures verify closed/single-stream validation, close-time availability, prefix-only snapshots, bidirectional
aware-time seek, deterministic restart position, dataset mismatch rejection, and terminal behavior.
Replay-persistence integration verifies restart reconstruction, idempotent session creation, exact next-event recovery,
optimistic version advancement, stale-writer rejection, dataset conflict rejection, and single-record durability.
Replay-coordinator integration verifies reload-before-use evidence checks, step/seek persistence, restart snapshots,
terminal no-op behavior, stale-client rejection, and failure on changed immutable datasets.
Replay-dataset integration verifies content-addressed idempotency, restart loading, digest reconstruction, missing-dataset
handling, input digest validation, and fail-closed detection of persisted metadata or payload tampering.
Replay-API integration verifies operator-only bounded dataset/session creation and step/seek mutations, authenticated
viewer snapshots, optimistic stale-client rejection, missing-dataset semantics, and request validation.
Replay HTTP request contracts and handlers are isolated in a dependency-injected router while integration coverage
continues to exercise the composed application, role dependencies, database transactions, and response semantics.
Replay discovery integration verifies authentication, bounded pagination, deterministic newest-first ordering, static
route resolution, metadata-only dataset responses, and payload integrity checks before dataset metadata is returned.
Replay-web integration verifies the responsive console and static assets are served, the document carries restrictive
CSP/no-store headers, credentials use tab-scoped session storage rather than persistent local storage, and the chart is
bounded to the latest 100 authorized prefix candles and constructed through safe SVG DOM APIs.
The replay console also offers operator-only, size-bounded local JSON dataset registration and session creation without
retaining dataset file contents in browser storage; server-side typed validation and content identity remain authoritative.
Authenticated replay users receive a bounded recent-session picker with safe DOM rendering, explicit selection/loading,
manual refresh, and automatic refresh after operator session creation.
Operator replay playback now launches the durable server scheduler with the current optimistic version, polls task and
prefix state, disables conflicting mutations, and invokes server stop on explicit pause or hidden-tab suspension.
The loaded session displays a bounded recent-run evidence table using text-only DOM construction and refreshes it at
task start and terminal transitions without exposing candle payloads or internal exception details.
Console context changes are task-safe: active playback blocks session selection, and disconnect or replay replacement
must successfully stop the owned server task before credentials or session context are discarded.
The console serializes the asynchronous playback-start transition and separates authoritative start/stop responses from
non-authoritative prefix or history refresh errors, avoiding duplicate starts and false ownership state.
Transient playback-status failures retain ownership and retry with bounded exponential delay; prefix refresh failures do
not abandon running tasks or conceal authoritative terminal scheduler outcomes.
Replay-scheduler integration verifies bounded cadence, serial optimistic versions, per-frame durable commits, restart
recovery, explicit completion/stop outcomes, injected clock/sleep behavior, and invalid rate/step-limit rejection.
Replay-task unit coverage verifies one active in-process owner per session, observable completion, cooperative stop,
graceful multi-task shutdown, missing-task behavior, and request-bound validation. Durable checkpoints remain the
restart authority; distributed ownership and durable task history are not yet implemented.
Replay-playback API integration verifies operator-only start/stop, viewer-readable task status, duplicate-owner
conflicts, bounded request validation, terminal completion evidence, prompt interruptible stops, and missing-task
responses. Active task ownership remains process-local and is not distributed.
Playback-run persistence records accepted requests and guarded terminal transitions under server-generated task IDs;
authenticated per-session history is bounded, newest-first, restart-readable, and excludes exception details. Running
task recovery and ownership remain process-local pending cross-process leases and orphan reconciliation.
Authenticated task-ID lookup provides stable restart-readable run evidence and reports process ownership only when the
serving process owns that exact running task rather than merely another run for the same replay session.
Current-playback reads survive restart by falling back to the latest persisted run and explicitly report whether the
task is owned by the serving process, preventing orphaned `running` evidence from masquerading as an active owner.
Portable-model security fixtures verify probability parity, canonical round trips, strict schema/format validation,
document-size and duplicate-field limits, non-finite and vector-size rejection, pickle rejection, and preservation
of future-feature guards.

## Blockers

No credential blocks current offline work. Owner verification of dated exchange, SEBI, tax, and broker charge
schedules is required before accepting Indian cost-model results. Broker credentials and owner compliance
decisions will be required for opt-in live tests/release.

## Definition of done

Each phase requires executable vertical behavior, migrations where relevant, deterministic tests, format,
lint, strict typing, security checks, runnable affected services, and updated docs. Platform production
readiness additionally requires the complete acceptance demonstration, sandbox contracts, restart recovery,
reconciliation, monitoring/alerts, tested backups, security gates, operational runbooks, and explicit owner
authorization. Profitability and regulatory approval are separate from software correctness.
