# Order lifecycle

The first Phase 8 execution slice is a pure deterministic state machine. It starts at `CREATED`, requires explicit
risk-pending and risk-approved events before submission, and represents submission uncertainty as
`RECONCILIATION_REQUIRED`. That state has no resubmission transition: a network timeout or unknown response can
never be interpreted as order failure or retried blindly.

Broker callbacks carry stable event IDs. Replaying an already processed event is a no-op, while timestamps older
than the last accepted event and conflicting broker order IDs fail closed for reconciliation. Fills may arrive from
`SUBMITTED`, `ACKNOWLEDGED`, `PARTIALLY_FILLED`, or `CANCEL_PENDING` because real broker streams can race an
acknowledgement or cancellation. Fill quantities are cumulative, cannot exceed requested quantity, and are retained
when a partially filled remainder is cancelled.

Terminal risk rejection, broker rejection, fill, cancellation, and expiry states do not accept unsupported events.
Every accepted transition increments an optimistic version and retains its processed event IDs. The pure machine
does not place an order and has no live-trading authority.

`ExecutionOrderRepository` persists the current state and every accepted source event in one caller-controlled
transaction. Updates compare the stored optimistic version and fail closed on concurrent modification. Restart
reconstruction restores status, quantities, broker identity, reconciliation reason, event IDs, and version; replaying
an already persisted callback remains a no-op. Broker reconciliation and adapters remain separate concerns.

Reconciliation compares broker-authoritative snapshots with local orders by broker identity. Unknown broker orders,
missing local/broker identities, duplicate mappings, quantity/fill differences, and status differences produce typed
issues and set `safe_to_trade` false. Pre-submission local states do not require a broker identity. Reconciliation
never silently edits local state; remediation must produce explicit lifecycle events after operator/adapter review.
The reconciliation safety flag is a separate independent risk-context input, so an uncertain result blocks new
entries while the bounded exit path remains available.
