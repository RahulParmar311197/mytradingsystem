# Options engine

The first Phase 9 slice implements a deterministic Black–Scholes baseline for European calls and puts with
continuous risk-free/dividend rates. It returns price, delta, gamma, annual theta, vega per 1.0 volatility change,
and rho per 1.0 rate change. Inputs use `Decimal` at the boundary; transcendental calculations necessarily use
binary floating point and results are converted back to `Decimal`. Time to expiry is an explicit positive year
fraction supplied by the caller, so exchange expiry time and holiday policy cannot be silently assumed.

Implied volatility uses bounded bisection between 0.000001 and 5.0, validates that market price lies within the
solvable model range, has explicit tolerance/iteration limits, and fails rather than returning a non-converged value.
Black–Scholes is a baseline, not a claim that Indian index/equity options follow its assumptions.

Chain analytics calculate open-interest put/call ratio and max pain across available strikes. Chain identity is
validated against every contract, quote instrument, expiry, underlying, and snapshot time. The liquidity gate
requires minimum volume and OI, positive two-sided depth, maximum spread, and a non-future fresh quote; last traded
price alone is never considered sufficient. Multi-leg expiry payoff supports signed quantities for long/short legs.

Portfolio aggregation scales each per-unit Greek by signed position quantity and contract lot size. Delta, gamma,
theta, vega, and rho retain the position sign, while marked options exposure is deliberately gross. The aggregate
is suitable as an input to the independent risk engine; it is not itself a risk approval.

IV percentile uses only unique observations available at the requested point in time and refuses undersized history.
Broker Greek comparison rejects stale/future calculations and reports every field outside configured absolute
tolerance. Delta selection considers only liquid contracts with fresh Greek evidence, then deterministically ranks
delta distance, spread, open interest, and strike.

Cross-expiry selection derives days-to-expiry from the Asia/Kolkata market date, applies inclusive configured day
bounds, rejects future chain snapshots, and supports an explicit nearest- or farthest-expiry preference. Each expiry
must still produce a liquid contract with fresh Greek evidence; expiry preference never bypasses contract controls.

The scenario margin estimator reports premium outlay, loss at every configured spot shock, maximum scenario loss,
and a configurable short-notional floor. Required margin is the maximum of those three components. It is deliberately
versioned and transparent, but is only a conservative research approximation: execution must use current broker or
clearing margin and must fail closed when authoritative margin is unavailable.

IV observations are persisted per instrument with provider event identity and observation timestamp uniqueness.
Repeated identical provider events are idempotent; conflicting reuse fails closed. History queries apply an inclusive
as-of cutoff in the database, return chronological observations, and therefore cannot expose later persisted values.

Normalized chain snapshots are stored as immutable typed payloads keyed by provider event identity, underlying,
expiry, observation time, and source. Ingest runs chain identity/time validation first; identical retries are
idempotent and conflicting event reuse fails closed. Retrieval selects only the latest snapshot at or before an
explicit cutoff and reconstructs the strict domain model, making restart behavior point-in-time reproducible.

The original provider payload is retained in a separate raw-event table under the same source/event identity. Raw and
normalized records are written in one session transaction. A retry must match both representations; an orphaned raw
or normalized record fails closed instead of being silently repaired, keeping forensic evidence distinct from the
domain projection.

American-style models, authoritative broker/clearing margin integration, and API endpoints remain Phase 9 work. Model
output is analytical evidence only and has no order authority; broker reconciliation of aggregated Greeks also
remains.
