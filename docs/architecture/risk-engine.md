# Independent risk engine

The initial Phase 7 risk authority is a pure deterministic layer with no strategy imports and no broker access.
It accepts a typed `OrderIntent`, current portfolio/market/operational context, explicit limits, a reference price,
and a stop. Its only result is a versioned `RiskDecision` that approves, resizes, or rejects the requested quantity.

New entries fail closed for a manual kill switch, broker disconnection, failed data quality, closed trading session,
event-risk lock, stale/future quote, abnormal spread, daily-loss breach, or maximum open positions. Approved sizing
is the minimum of requested quantity, equity risk divided by stop distance, and remaining per-instrument exposure.
Missing stops, exhausted exposure, invalid quotes, and invalid capital are rejected with stable reason codes.

The same entry-lock evaluation enforces weekly loss, portfolio drawdown, gross and absolute net exposure, orders per
minute, and consecutive-loss circuit breaking. Boundaries are inclusive: reaching a configured ceiling locks new
entries. Counters and drawdown are validated before evaluation, and these locks do not weaken the exit path.
Sector exposure, strategy allocation, expected slippage, and an explicit cooldown-until timestamp add further
independent entry locks. Daily/weekly loss, drawdown, or consecutive-loss breaches can activate the same durable,
audited kill switch under the `risk-engine` actor; safe contexts do not change safety state.

For options, the context carries current and proposed gross marked exposure plus signed portfolio delta and gamma.
The authority evaluates projected post-order values and rejects new entries that would exceed any independently
configured options exposure, absolute delta, or absolute gamma ceiling. These limits are effective-dated and required
by the persistent configuration store like every other production risk limit.

Exit intents take a deliberately separate path: entry locks do not strand an existing position. An exit is bounded
to the absolute current position and rejected when no position exists. This permits safe reduction during a kill
switch without allowing the exit request to reverse or increase exposure.

`PersistentRiskAuthority` stores the final decision, policy version, reason codes, account/instrument identity, and
a SHA-256 fingerprint of every decision input. Re-evaluating the identical intent after restart returns the original
decision; reusing that intent with changed risk inputs fails closed. The database uniqueness constraint on intent ID
is the final duplicate-decision guard.

`PersistentRiskConfigurationStore` loads the latest enabled value effective at the evaluation timestamp for every
required limit. A missing limit fails closed; future revisions are never visible early. The derived policy version
fingerprints the selected records. Manual kill-switch changes persist actor, reason, correlation ID, UTC timestamp,
and an audit event, and the state survives service restart.

Automatic cooldown calculation, graceful concurrent-conflict recovery, and property tests remain Phase 7 work;
therefore this module is not yet the complete production risk engine.
