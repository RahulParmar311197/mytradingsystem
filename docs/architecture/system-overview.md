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
