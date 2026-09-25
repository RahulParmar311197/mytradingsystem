# System overview

## Architecture decision

The platform is a modular monolith with separately deployable API and future worker/web processes. Domain
contracts have no broker dependency. PostgreSQL is authoritative state; Redis will provide ephemeral
coordination, never order truth. This avoids premature microservices while retaining extraction boundaries.

The mandatory order path is:

`validated market data → feature engine → strategy signal → decision engine → independent risk engine → execution policy → broker adapter → reconciliation`

No model or strategy may call a broker. Execution APIs will require a persisted approving risk decision.
Unknown submission outcomes enter reconciliation rather than retry. Paper and live adapters will share one
interface, but there is no fallback from paper to live.

## Phase 1 boundary

The API exposes liveness/readiness and metrics with correlation/security headers. Pydantic contracts enforce
UTC timestamps and decimal precision. SQLAlchemy/Alembic persist trading accounts, versionable risk limits,
append-oriented audit events, and durable safety state. Environment configuration defaults to paper and live
startup requires every independent interlock plus the exact explicit confirmation phrase.

## Trust boundaries

Broker and market-data networks are untrusted inputs. Secrets enter only through environment/secret-provider
interfaces and logs redact recognized secret fields. PostgreSQL and audit availability will be mandatory for
execution. Authentication, authorization, request rate limiting, and the execution path remain later work;
therefore this foundation is not production ready.

## Historical market-data boundary

Provider contracts return domain instruments and candles without exposing broker-specific payloads. Ingestion
first stores a source event in the raw table, validates it, writes explicit quality events, and only then writes
valid normalized candles; unique source IDs and candle identities make retries idempotent. Invalid data is never
silently corrected. Higher timeframes align to the 09:15–15:30 Asia/Kolkata regular NSE session and require a
complete, contiguous set of source bars whose closing time is no later than the caller's point-in-time cutoff.

## Technical feature boundary

The indicator package is a pure, provider-independent calculation layer. Every output is index-aligned with
its source, represents unavailable warm-up observations as `None`, rejects non-finite input, and reads no
observation after the output index. Confirmed pivots are emitted only after their configured right-hand window
has closed, so downstream strategies cannot see a pivot before it was knowable. Indicator floats are derived
features rather than monetary ledger values; prices remain `Decimal` at domain and persistence boundaries.

The SMC/ICT layer consumes only chronological, closed candles from one instrument/timeframe. Its versioned,
deterministic rules return immutable evidence timestamps, invalidation conditions, explanations, and neutral
overlay primitives. A newly confirmed swing cannot be broken by its own confirmation candle. These analytical
labels remain upstream features: they cannot access execution and cannot bypass the decision or risk engines.
Zone lifecycle is derived afresh from the caller's candle snapshot: FVG state changes use only later closed
candles, inverse zones require a close through the source boundary, and overlays never extend past `as_of`.
Displacement and equal-level liquidity are likewise emitted only at candle close or second-swing confirmation.
MSS composes an opposing structural break with same-candle displacement and retains both evidence sets.
Interval timestamps represent candle opens, so analytical availability is recorded at timestamp plus timeframe.
Indian reference levels group in Asia/Kolkata and never include a later local date/week. Dealing-range zones use
confirmed swings only; fixed-IST kill-zone labels explicitly avoid pretending to be DST-aware foreign sessions.
Block lifecycle is causal and finite: only displacement-confirmed breaks can select an opposing origin candle,
mitigation requires a later overlap, and breaker conversion requires a later directional close-through.
Internal and external structure share the strict swing rule but maintain independent windows and trend state.
Only external structure feeds block detection; both scopes emit clearly labelled neutral overlay records.

The regime layer consumes one already validated point-in-time feature snapshot and returns independent trend,
volatility, liquidity, and event-risk axes. It has no market-data retrieval or execution dependency. Event risk
creates an explicit new-entry lock while preserving the other explanatory classifications.

Strategies consume immutable feature/regime snapshots and emit proposed signals only. Their common result has
explicit NO_TRADE reasons, levels, explanation, version, snapshot ID, and a capped risk-fraction request; it has
no broker method or quantity authority. The decision and future independent risk engines remain mandatory.

The decision engine combines bounded evidence scores, validates entry geometry and minimum risk/reward, and
fails to NO_TRADE on weak confidence or data quality. Optional ML is removed and weights renormalized when it is
unavailable. Every entry remains explicitly pending independent risk approval; descriptive risk context is not
an approval and cannot bypass Phase 7.

The backtester consumes the same decision contract, supplies only causal candle prefixes, queues all decisions
to the next candle, and delegates sizing/rejection to a risk-policy protocol. Its default policy is explicitly a
research approximation, not the production risk engine. Ambiguous intrabar exits resolve stop-first.
Research validation remains chronological: train/validation/test partitions and walk-forward folds never shuffle
time, while seeded Monte Carlo is explicitly limited to trade-ordering risk.

The initial paper execution adapter accepts only an intent plus its matching independent risk approval. Market
fills, charges, positions, and lifecycle evidence share one caller-controlled database transaction, while a
database uniqueness constraint prevents a committed idempotency key from producing another fill after restart.
Its cash ledger and point-in-time marks persist equity, P&L, exposure, and drawdown. It is explicitly paper-only
and has no live fallback.

The independent risk layer has no strategy or broker dependency. Its first deterministic policy blocks new entries
on operational/data/session/event/kill-switch locks, applies stop-distance and exposure sizing, and emits only a
versioned risk decision. Exit intents remain bounded to the current position but available during entry locks.
Final decisions are keyed by intent and persisted with an input fingerprint so restart retries are stable and an
attempt to mutate already-decided risk inputs fails closed.

The execution lifecycle is a deterministic event reducer. Unknown submission outcomes enter
`RECONCILIATION_REQUIRED`, duplicate callbacks are idempotent, conflicting/out-of-order evidence fails closed, and
partial fills remain accounted for through cancellation. Persistence and broker adapters remain Phase 8 work.
