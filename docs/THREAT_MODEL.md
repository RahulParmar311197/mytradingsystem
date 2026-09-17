# Threat model

| Boundary / threat | Current control | Remaining work |
|---|---|---|
| Forged configuration enables trading | Live API/worker startup refused | Runtime risk authorization and broker reconciliation |
| Data JSON bypasses temporal validation | Validate parsed dates and normalize UTC | Provider arrival-time and revision provenance |
| Missing DB schema masquerades as ready | Check Alembic head and safety/audit tables | Full migration/concurrency checks in PostgreSQL CI |
| Secret leakage via logs and errors | Output redaction; no exception payloads; no raw request logging | Broker-specific payload contracts and security review |
| Kill-switch update without audit | Single database transaction | DB immutability and authenticated operator identities |
| Metrics exhaustion via random routes | Labels use route templates or unmatched | Distributed request quotas |
| Container escape / overprivilege | Non-root, read-only, no caps, loopback ports | Production TLS, network isolation, OS baseline |
| Package substitution | Pinned lock plus artifact hashes | Scheduled updates and full supply-chain review |

The local operator and migration owner are privileged identities. SQLite is outside the production
trust boundary. No model, broker order API, or public trading endpoint exists in this release.
