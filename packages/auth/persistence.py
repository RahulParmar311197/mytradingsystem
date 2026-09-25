"""Durable, point-in-time API token revocation evidence."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models import AuditEventRecord, RevokedAPITokenRecord


class PersistentTokenRevocationStore:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def revoke(
        self,
        *,
        token_sha256: str,
        revoked_at: datetime,
        actor_id: str,
        reason: str,
        correlation_id: str,
    ) -> RevokedAPITokenRecord:
        _validate_digest(token_sha256)
        _validate_time(revoked_at)
        revoked_at = revoked_at.astimezone(UTC)
        if not actor_id.strip() or not reason.strip() or not correlation_id.strip():
            raise ValueError("revocation actor, reason, and correlation ID are required")
        existing = await self.session.scalar(
            select(RevokedAPITokenRecord).where(RevokedAPITokenRecord.token_sha256 == token_sha256)
        )
        if existing is not None:
            if (
                existing.actor_id != actor_id
                or existing.reason != reason
                or existing.correlation_id != correlation_id
            ):
                raise ValueError("token digest already has conflicting revocation evidence")
            return existing
        record = RevokedAPITokenRecord(
            token_sha256=token_sha256,
            revoked_at=revoked_at,
            actor_id=actor_id,
            reason=reason,
            correlation_id=correlation_id,
        )
        self.session.add(record)
        self.session.add(
            AuditEventRecord(
                occurred_at=revoked_at,
                actor_id=actor_id,
                action="api_token.revoke",
                resource_type="api_token_digest",
                resource_id=token_sha256,
                outcome="success",
                correlation_id=correlation_id,
                details={"reason": reason},
            )
        )
        await self.session.flush()
        return record

    async def is_revoked(self, token_sha256: str, *, as_of: datetime) -> bool:
        _validate_digest(token_sha256)
        _validate_time(as_of)
        as_of = as_of.astimezone(UTC)
        record = await self.session.scalar(
            select(RevokedAPITokenRecord).where(
                RevokedAPITokenRecord.token_sha256 == token_sha256,
                RevokedAPITokenRecord.revoked_at <= as_of,
            )
        )
        return record is not None


def _validate_digest(value: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("token digest must be a lowercase SHA-256 value")


def _validate_time(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("revocation timestamp must be timezone-aware")
