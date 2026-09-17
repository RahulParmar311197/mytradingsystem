# Security boundary

This development release does not support live execution or production user access.
The API refuses live startup even when environment flags claim all interlocks passed.
Only liveness/readiness/metrics are public foundation endpoints. Operator mutation is local CLI.
Keep development listeners on loopback. Do not expose this release to the Internet.

- Configuration uses external environment values; `.env` is ignored and excluded from image context.
- `scripts/configure_local.py` creates random credentials with mode 0600 and exclusive creation.
- Application DB role is not a superuser; migrations run with the owner role.
- Settings omit DB URLs from representations. SQLAlchemy hides bound parameters.
- Final log output recursively redacts recognized secret/PII keys, bearer values, and URL credentials.
  Arbitrary unlabeled text cannot be reliably identified as secret: never log raw broker payloads,
  request bodies, exception strings, or account identifiers. Error responses omit validation inputs.
- Runtime images run as UID 10001, with read-only roots, dropped capabilities, and no new privileges.
- CORS rejects wildcard origins. Production configuration requires PostgreSQL, Redis checks, and HTTPS origins.
- Runtime dependency hashes and locks are checked in. CI audits dependencies and containers.

Authentication, refresh rotation, RBAC, distributed rate limits, database-enforced audit immutability,
TLS ingress, secret-manager rotation, and production backup verification remain release blockers.
Do not interpret static analysis or dependency scan success as a complete security assessment.
