# API authentication and authorization

Phase 11 begins with fail-closed authentication for non-health application routes. Liveness, readiness, and metrics
retain their existing deployment-facing behavior; `/api/v1/*` routes require an opaque bearer token. If no API token
is configured, protected routes return service-unavailable rather than becoming anonymous.

Viewer and operator tokens must be distinct and at least 32 characters. Settings hold them as secret values, while the
runtime authenticator retains only SHA-256 digests and uses constant-time comparisons. Tokens are deployment secrets:
examples contain empty placeholders, logs must not include authorization headers, and production values must come from
a secret manager. This initial static-token boundary is suitable for controlled deployments, not public multi-user
identity; external OIDC, dynamic revocation, session management, and durable user/audit records remain required.

Deployments can perform one-window token rotation by configuring distinct previous viewer/operator tokens with one
timezone-aware expiry. Current and previous digests are compared using the same constant-time path; previous tokens are
rejected at or after the deadline. A previous token without an expiry, naive expiry, duplicate token, or short token
fails configuration. This grace mechanism is not a replacement for dynamic revocation or identity-provider sessions.

For immediate deployment-driven revocation, configuration accepts unique lowercase SHA-256 token digests. Revocation
checks use constant-time digest comparison and override both current and previous-token matches without storing the
revoked plaintext. Applying a changed list requires configuration reload/restart; dynamic durable revocation remains
the responsibility of a future identity service.

A persistent revocation repository stores one immutable digest, UTC-effective timestamp, actor, and reason. Identical
retries are idempotent, conflicting evidence fails closed, and as-of queries exclude future-effective revocations.
When persistent checks are explicitly enabled after migration, every authenticated request queries this repository at
the current UTC time. A revoked credential returns the same generic `401` as any invalid token; database or schema
failure returns `503` and denies access. The authenticating credential digest stays internal and is never included in
session or mode responses.

The operator-only revocation endpoint accepts a digest and reason, derives actor and correlation identity from the
authenticated request, and atomically writes the revocation plus a general audit event. Repeating the same actor,
reason, digest, and correlation identity returns the original revocation without duplicating audit evidence; conflicting
reuse returns `409`. Viewer access is forbidden and write infrastructure failures deny the operation with `503`.
External identity administration remains before this is a complete identity-management surface.

The role hierarchy is deliberately small: operators inherit viewer access, but viewers cannot access operator routes.
Authentication failures return `401` with a Bearer challenge, authorization failures return `403`, and absent server
configuration returns `503`. The initial authenticated endpoints are read-only and cannot change trading mode, risk
state, broker state, or place orders.
