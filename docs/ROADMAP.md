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
  benchmark comparison, and cost sensitivity are tested; advanced orders, Indian charges, extended reports, and
  full out-of-sample orchestration remain.
- [ ] **Phase 6:** persistent paper broker, accounting, journal, and analytics.
- [ ] **Phase 7:** independent persisted risk evaluation and manual/automatic kill switches.
- [ ] **Phase 8:** contract-tested Upstox/Dhan adapters, durable order state machine and reconciliation.
- [ ] **Phase 9:** option chains, liquidity gates, Black-Scholes Greeks and portfolio options risk.
- [ ] **Phase 10:** optional point-in-time ML scoring, registry, calibration, drift and deterministic fallback.
- [ ] **Phase 11:** authenticated responsive web application, replay and end-to-end/recovery hardening.
- [ ] **Phase 12:** controlled release evidence; live remains off until owner/regulatory authorization.
