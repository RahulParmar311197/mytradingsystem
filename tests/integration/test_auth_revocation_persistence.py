from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.auth import PersistentTokenRevocationStore
from packages.database.base import Base
from packages.database.models import AuditEventRecord, RevokedAPITokenRecord


@pytest.mark.asyncio
async def test_revocation_persists_idempotently_and_survives_restart() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    digest = sha256(b"compromised-token").hexdigest()
    now = datetime(2026, 9, 21, 6, tzinfo=UTC)
    async with sessions() as session:
        store = PersistentTokenRevocationStore(session)
        first = await store.revoke(
            token_sha256=digest,
            revoked_at=now,
            actor_id="security-operator",
            reason="credential exposed",
            correlation_id="incident-123",
        )
        second = await store.revoke(
            token_sha256=digest,
            revoked_at=now,
            actor_id="security-operator",
            reason="credential exposed",
            correlation_id="incident-123",
        )
        assert first.id == second.id
        await session.commit()
    async with sessions() as session:
        store = PersistentTokenRevocationStore(session)
        assert not await store.is_revoked(digest, as_of=now - timedelta(microseconds=1))
        assert await store.is_revoked(digest, as_of=now)
        assert await session.scalar(select(func.count()).select_from(RevokedAPITokenRecord)) == 1
        assert await session.scalar(select(func.count()).select_from(AuditEventRecord)) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_revocation_rejects_conflicting_or_invalid_evidence() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    digest = sha256(b"compromised-token").hexdigest()
    now = datetime(2026, 9, 21, 6, tzinfo=UTC)
    async with sessions() as session:
        store = PersistentTokenRevocationStore(session)
        await store.revoke(
            token_sha256=digest,
            revoked_at=now,
            actor_id="security-operator",
            reason="credential exposed",
            correlation_id="incident-123",
        )
        with pytest.raises(ValueError, match="conflicting"):
            await store.revoke(
                token_sha256=digest,
                revoked_at=now,
                actor_id="another-operator",
                reason="different evidence",
                correlation_id="incident-456",
            )
        with pytest.raises(ValueError, match="SHA-256"):
            await store.is_revoked("bad", as_of=now)
        with pytest.raises(ValueError, match="timezone-aware"):
            await store.is_revoked(digest, as_of=datetime(2026, 9, 21))
        await session.rollback()
    await engine.dispose()
