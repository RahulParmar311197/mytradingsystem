# Changelog

## Unreleased

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
- Audit the initially empty repository and document architecture/status/roadmap.
- Add Phase 1 configuration safety interlocks, typed domain contracts, persistence/migration, observability,
  health API, development containers, CI gates, and tests.
- Add the Phase 2 historical-data slice: provider contracts, instrument/raw/normalized persistence,
  idempotent ingestion, visible quality events, and point-in-time NSE-aligned candle aggregation.
