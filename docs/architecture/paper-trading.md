# Persistent paper trading

The initial Phase 6 vertical slice executes market orders only. `PersistentPaperBroker` accepts an `OrderIntent`
and a separate `RiskDecision`; it refuses execution unless the decision belongs to that exact intent and has an
`APPROVED` or `RESIZED` outcome. A resize can reduce but never increase the requested quantity. This preserves the
mandatory decision → independent risk → execution boundary.

Every fill, order, resulting position, and lifecycle event is written through the caller's single database
transaction. The `(account_id, idempotency_key)` database constraint is the final duplicate-order guard. Repeating
an already committed request, including after constructing a new broker instance following restart, returns the
original execution and cannot create a second fill or position update.

Market fills apply configurable adverse slippage and the same pluggable cost protocol used by backtests. Position
accounting supports increasing, reducing, closing, and reversing long/short positions; realized P&L and charges are
persisted. Timestamps must be timezone-aware and are normalized to UTC. The persisted event explicitly records
paper mode.

Each paper account has an idempotently initialized cash ledger. Buys debit notional plus charges and sells credit
notional minus charges. Point-in-time marking requires a positive price for every open position, then persists cash,
realized and unrealized P&L, equity, gross/net exposure, peak-equity drawdown, and per-position marks. Missing or
stale-price policy remains the caller's responsibility; the broker refuses a snapshot when an open price is absent.

This slice does not yet support pending limit/stop orders, partial fills, cancellation/modification, margin,
holdings, end-of-day reconciliation, concurrent duplicate response recovery, or the trade journal. The unique
constraint prevents a concurrent duplicate from creating two orders, but graceful
recovery of the losing transaction remains follow-up work. It is not a live broker and cannot fall back to live.
