# Changelog

## Unreleased

- Add authenticated durable replay-run lookup by server-generated task ID.
- Retain server-playback ownership across transient status/prefix failures with bounded polling backoff.
- Serialize replay playback startup and treat post-start evidence refresh failures as non-authoritative UI errors.
- Stop owned server playback before disconnecting, changing sessions, or creating a replacement replay.
- Show bounded, safely rendered server-playback history in the replay console.
- Drive replay-console playback through the durable server scheduler with polling, stop, and hidden-tab shutdown.
- Recover the latest persisted replay playback status after process restart with explicit ownership evidence.
- Persist replay playback-run lifecycle evidence and expose bounded authenticated per-session history.
- Add operator replay-playback start/stop APIs, authenticated playback status, and interruptible task shutdown.
- Add single-process replay-task ownership with one active task per session, cooperative stop, observable terminal
  status, and graceful shutdown.
- Add a bounded server-side replay scheduler with per-frame durable commits and restart-safe outcomes.
- Add bounded operator replay playback with pause, terminal/error stops, and hidden-tab suspension.
- Add an authenticated recent-session picker to the replay console.
- Add authenticated, bounded recent-dataset and replay-session discovery endpoints.
- Extract replay HTTP contracts and handlers into a dedicated dependency-injected API router.
- Add an operator-only replay JSON upload workflow that registers a dataset and opens a new session.
- Render a bounded dependency-free candlestick and volume chart from the authorized replay prefix.
- Add a responsive, CSP-hardened replay console with tab-scoped credentials and role-aware controls.
- Add authenticated replay dataset/session APIs with operator mutations, viewer snapshots, and optimistic versions.
- Persist immutable content-addressed replay datasets with reconstruction and load-time integrity verification.
- Coordinate replay step/seek/snapshot operations through immutable dataset reload and optimistic checkpoints.
- Persist dataset-bound replay checkpoints with optimistic concurrency and restart recovery.
- Start deterministic Phase 11 closed-candle replay with prefix-only seek and dataset-bound checkpoints.
- Add an operator-only idempotent token-revocation API with atomic audit evidence.
- Enforce optional persistent token revocation checks on each protected API request with fail-closed lookup errors.
- Persist idempotent point-in-time API token revocation evidence without token plaintext.
- Add configuration-driven bearer-token revocation using validated SHA-256 digests.
- Add bounded previous-token rotation grace with a mandatory timezone-aware expiry.
- Start Phase 11 with fail-closed bearer authentication, viewer/operator RBAC, and read-only protected API endpoints.
- Add a metadata-only MLflow experiment exporter with explicit non-authority and no-promotion tags.
- Add a contract-tested S3 artifact-client adapter with conditional writes and bounded streaming reads.
- Add a vendor-neutral remote ML artifact boundary with conditional creation and verified evidence URIs.
- Add strict JSON-only portable reconstruction for logistic inference without executable deserialization.
- Add a bounded deterministic gradient-boosting challenger with chronological validation and feature evidence.
- Add checksum-verified, content-addressed local ML artifact storage that never deserializes model bytes.
- Add a bounded deterministic random-forest challenger with chronological validation and feature evidence.
- Add chronological three-window Platt calibration with independent out-of-calibration validation.
- Add explicit metric/guardrail champion-challenger comparison without automatic model promotion.
- Persist a checksum-aware metadata-only model registry and idempotent point-in-time prediction evidence.
- Add logistic calibration diagnostics, versioned coefficient importance, and point-in-time PSI drift monitoring.
- Start Phase 10 with a versioned, point-in-time logistic baseline and chronological validation metrics.
- Retain raw option-chain provider events separately and transactionally alongside normalized snapshots.
- Persist validated normalized option-chain snapshots with provider idempotency and latest-as-of recovery.
- Add a versioned, evidence-rich option scenario margin approximation for research-only workflows.
- Add India-date, DTE-bounded option expiry selection without bypassing liquidity or Greek freshness controls.
- Persist idempotent option IV observations with restart-safe point-in-time history queries.
- Add point-in-time IV percentile, broker Greek tolerance comparison, and liquid delta-based contract selection.
- Aggregate signed lot-aware portfolio Greeks and enforce persisted projected options exposure/delta/gamma limits.
- Add Black–Scholes valuation/Greeks/IV, option-chain PCR/max pain, liquidity gates, and expiry payoff analytics.
- Add risk-gated Upstox and Dhan v2 place/details/cancel adapters with mock-transport contracts and no placement retry.
- Add fail-closed broker/local order reconciliation with typed identity, quantity, fill, and status discrepancies.
- Persist execution order state and immutable events with optimistic concurrency and restart reconstruction.
- Add a deterministic idempotent order lifecycle with partial fills, cancellation races, and fail-closed unknown
  submission handling.
- Add sector/strategy allocation, slippage and cooldown locks plus audited automatic kill-switch activation.
- Enforce persisted weekly-loss, drawdown, gross/net exposure, order-rate, and consecutive-loss entry locks.
- Load effective-dated risk limits without future leakage and persist audited manual kill-switch state across restart.
- Persist final independent risk decisions idempotently with policy/reason evidence and immutable-input fingerprints.
- Add the first independent Phase 7 risk policy with fail-closed entry locks, deterministic sizing, reason-coded
  decisions, and bounded exits that remain available during entry locks.
- Add persistent paper cash accounting and point-in-time portfolio/P&L/exposure/drawdown snapshots.
- Add the first persistent Phase 6 paper-broker slice with mandatory risk approval, idempotent market fills,
  slippage/costs, position accounting, and lifecycle events.
- Add leakage-resistant out-of-sample candidate selection with a single held-out evaluation and immutable score
  audit.
- Add immutable Asia/Kolkata-aware backtest performance reports with daily/monthly returns, Sortino, Calmar,
  exposure, and direction breakdowns.

- Added the first Phase 3 vertical slice: causal technical indicators with explicit warm-up behavior,
  non-finite input rejection, confirmed non-repainting pivots, and deterministic unit fixtures.
- Added deterministic SMC/ICT v1 rules for confirmed swings, BOS/CHOCH, liquidity sweeps, three-candle FVGs,
  evidence and invalidation metadata, plus frontend-neutral chart overlays.
- Added point-in-time FVG mitigation/invalidation state, consequent encroachment, close-confirmed inverse FVGs,
  transition evidence, and snapshot-bounded overlays.
- Added configurable displacement, confirmed equal-high/equal-low liquidity bands, and an MSS rule requiring
  CHOCH plus aligned same-candle displacement.
- Added point-in-time IST previous-period/session levels, confirmed premium/discount and OTE zones, configurable
  kill-zone classification, and corrected analytical availability timestamps to candle close.
- Added displacement-confirmed order blocks with first-retest mitigation events, close-through invalidation,
  opposite breaker conversion, evidence, overlays, and prefix lifecycle tests.
- Added independently configurable internal/external swings and scoped BOS/CHOCH/MSS streams, with an explicit
  external-only boundary for price-block creation.
- Started Phase 4 with a versioned deterministic regime classifier covering trend, volatility, liquidity, and
  event risk with supporting features and an explicit entry-permission flag.
- Added the five initial versioned deterministic strategies behind a common context/result contract with shared
  session, event-risk, liquidity, and regime gates and explicit NO_TRADE outcomes.
- Completed the Phase 4 backend with an explainable weighted decision engine, optional-ML fallback, data-quality
  and price-geometry gates, risk/reward validation, and mandatory independent-risk-approval marking.
- Started Phase 5 with a next-candle event-driven backtester, conservative stop/target handling, actual-fill risk
  validation, configurable slippage/costs, rejection audit, trade ledger, curves, and core metrics.
- Added chronological splits, rolling/expanding walk-forward folds, deterministic Monte Carlo sequence analysis,
  parameter-stability checks, cost sensitivity, and aligned benchmark comparison.
- Added a pluggable, effective-dated India transaction-charge model with component breakdowns and intentionally
  omitted unverified statutory defaults pending official-source owner verification.
- Audit the initially empty repository and document architecture/status/roadmap.
- Add Phase 1 configuration safety interlocks, typed domain contracts, persistence/migration, observability,
  health API, development containers, CI gates, and tests.
- Add the Phase 2 historical-data slice: provider contracts, instrument/raw/normalized persistence,
  idempotent ingestion, visible quality events, and point-in-time NSE-aligned candle aggregation.
