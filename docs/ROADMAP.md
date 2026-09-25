# Roadmap

Work proceeds in dependency order; a checked item means code and automated verification exist.

- [x] **Phase 0:** empty-repository audit, architectural baseline, security default review.
- [x] **Phase 1 slice:** typed domain contracts, fail-closed configuration, database models/migration,
  structured logging/redaction, health/metrics API, Docker development services, and CI foundation.
- [x] **Phase 2 slice:** instrument master plus historical ingestion, explicit quality events, idempotency, and
  closed-candle multi-timeframe aggregation with leakage tests.
- [x] **Phase 3 backend:** causal indicators plus versioned scoped swings, BOS/CHOCH, liquidity sweeps, lifecycle
  FVG/IFVG, displacement, MSS, equal-level liquidity and consequent encroachment, explanations and overlay
  contracts are tested. IST reference levels, premium/discount, OTE, and fixed-IST kill zones are tested;
  displacement-confirmed order/mitigation/breaker blocks and independent internal/external structure are tested.
  Browser rendering remains part of the Phase 11 frontend rather than being falsely marked complete here.
- [x] **Phase 4 backend:** transparent multi-axis regime classifier, five deterministic strategies, and the
  explainable decision engine are tested. Entry decisions still require the independent Phase 7 risk engine.
- [ ] **Phase 5 (in progress):** next-candle event-driven market fills, slippage/costs, risk rejection, ledger,
  equity/drawdown, core metrics, chronological splits, walk-forward folds, parameter stability, seeded Monte Carlo,
  benchmark comparison, cost sensitivity, configurable India charge formulas, daily/monthly returns, Sortino,
  Calmar, exposure, direction reports, and leakage-resistant held-out selection are tested; official rate
  verification, advanced orders, and extended reports remain.
- [ ] **Phase 6 (in progress):** risk-gated persistent paper market fills, restart-safe idempotency, lifecycle audit,
  cash ledger, position accounting, portfolio marks, P&L/exposure snapshots are tested; advanced orders, margin,
  holdings, journal, and extended analytics remain.
- [ ] **Phase 7 (in progress):** independent deterministic entry locks, stop/exposure sizing, reason-coded decisions,
  kill-switch-safe bounded exits, idempotent decisions, effective-dated limits, and audited persistent manual kill
  state are tested. Weekly loss, drawdown, gross/net exposure, order-rate and consecutive-loss locks are tested;
  sector/strategy allocation, slippage, cooldown locks, automatic kill activation, and projected options
  exposure/delta/gamma ceilings are tested. Automatic cooldown derivation, concurrent-conflict recovery, and property
  tests remain.
- [ ] **Phase 8 (in progress):** the deterministic order lifecycle, duplicate callbacks, partial fills,
  cancellation, unknown-submission reconciliation, optimistic persistence, immutable events, and restart recovery
  are tested. Broker/local discrepancy detection fails closed; remediation workflows and contract-tested Upstox/Dhan
  place/details/cancel mappings exist. Remaining broker capabilities, remediation workflows, and sandbox validation
  remain.
- [ ] **Phase 9 (in progress):** Black–Scholes Greeks/IV, PCR, max pain, chain validation, liquidity gates, payoff, and
  signed lot-aware portfolio Greek aggregation are tested. Point-in-time IV percentile, tolerance-based broker Greek
  comparison, liquid delta/expiry selection, and idempotent as-of IV/normalized-chain persistence are tested. Raw
  provider events are retained separately and transactionally paired with normalized snapshots. Authoritative margin
  integration and reconciliation remain. A versioned scenario margin approximation is available for research only.
- [ ] **Phase 10 (in progress):** a versioned point-in-time logistic baseline, chronological train/validation split,
  leakage guards, Brier/log-loss/calibration-error evaluation, coefficient importance, point-in-time PSI drift, and
  versioned predictions are tested. Metadata-only registry stages and idempotent evidence-rich prediction logging are
  persisted; explicit primary/guardrail champion comparison is tested without automatic promotion. Artifact
  bytes have checksum-verified local storage without deserialization, the injected remote object-store boundary uses
  digest-derived keys and conditional creation, and the logistic baseline has strict JSON-only portable reconstruction;
  contract-tested S3 and metadata-only MLflow adapters exist, while live service validation remains. Platt calibration
  uses dedicated chronological calibration and validation windows; bounded deterministic random-forest and
  gradient-boosting challengers are tested.
- [ ] **Phase 11 (in progress):** fail-closed opaque bearer authentication, viewer/operator RBAC, secret validation,
  bounded previous-token rotation grace, configuration-driven digest revocation, and read-only session/mode endpoints
  are tested. Restart-safe, point-in-time revocation persistence is enforced per request with fail-closed dependency
  handling when enabled; an idempotent operator-only revocation workflow emits atomic audit evidence. External identity,
  the broader authenticated application, advanced replay charts, and end-to-end/recovery hardening remain. A responsive
  replay console provides tab-scoped authentication, role-aware prefix inspection, operator step/seek controls, and a
  bounded closed-candle price/volume chart with an accessible evidence table. Operators can register bounded local JSON
  datasets and create sessions without persisting file contents in the browser; authenticated users can discover and
  select recent sessions without manually transferring UUIDs. Operators launch and monitor bounded server playback
  from the console, including explicit and hidden-tab stops. A bounded server scheduler commits each emitted frame and
  exposes deterministic complete/stopped/
  step-limit outcomes; a single-process task manager enforces one active owner per session with cooperative shutdown,
  and authenticated APIs expose operator start/stop plus viewer status. The console safely renders recent durable run
  evidence, while current status falls back to persisted evidence after restart with explicit process-ownership
  metadata. Cross-process
  leases and orphan reconciliation remain. A
  deterministic closed-candle prefix replay engine, aware-time seek, dataset-bound checkpoints, restart persistence,
  optimistic checkpoint concurrency, immutable-loader reconstruction orchestration, and content-addressed database
  dataset storage with load-time integrity verification are tested. Authenticated operator dataset/session creation and
  version-checked step/seek endpoints expose replay safely, with viewer-only prefix reads and bounded recent
  dataset/session discovery.
- [ ] **Phase 12:** controlled release evidence; live remains off until owner/regulatory authorization.
