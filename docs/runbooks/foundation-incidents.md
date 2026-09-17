# Foundation incident procedures

## Database outage or missing schema

Stop new work; never substitute in-memory persistence. `/health/ready` must return 503.
Inspect database availability and migration revision without printing connection credentials.
Apply reviewed forward migrations using the owner role. Restart API/worker and recheck readiness.
Verify persisted risk limits and kill-switch state before any future trading-capable release resumes.

## Redis outage

Production readiness fails. The worker locks entries when the database remains available.
Restore Redis, verify health, inspect the durable safety state, and keep the lock on pending review.
Restart must not automatically unlock it. Redis never contains authoritative order state.

## Kill switch and abnormal loss

Run `python -m apps.manage kill-switch on --reason 'incident reference'` with configured operator
DB access, then verify `python -m apps.manage safety`. Inspect the audit event. Record the incident
outside logs if it contains personal information. Unlock only after cause and state are understood.
This foundation does not implement execution, liquidation, or exit-order management.

## Credential rotation

Lock entries. Replace secret values in the deployment secret source and the PostgreSQL role,
restart dependent services, and validate readiness. Never paste tokens in tickets, logs, or Git.
Broker rotation is pending broker-specific integrations.

## Rollback and backup restoration

Preserve current DB backup and audit records. Roll back application image only to a version compatible
with the current schema; otherwise apply a reviewed forward fix. Do not downgrade production tables
using disposable CI tests. Restore to an isolated database, validate migrations and safety state,
and compare row counts before switching any service. A production restore drill is not yet certified.

Broker outage, market-data outage, unknown orders, position mismatches, and reconciliation procedures
will be implemented with their corresponding execution/data slices; no such live service exists yet.
