from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database import Base
from packages.database.models import ReplaySessionRecord
from packages.domain.models import Candle
from packages.replay import ReplayEngine, ReplaySessionRepository

NOW = datetime(2026, 9, 24, 4, tzinfo=UTC)
INSTRUMENT_ID = uuid4()


def engine(count: int = 4) -> ReplayEngine:
    return ReplayEngine(
        tuple(
            Candle(
                instrument_id=INSTRUMENT_ID,
                timestamp=NOW + timedelta(minutes=index),
                timeframe_seconds=60,
                open=Decimal(100 + index),
                high=Decimal(102 + index),
                low=Decimal(99 + index),
                close=Decimal(101 + index),
                volume=Decimal(1000),
            )
            for index in range(count)
        )
    )


@pytest.mark.asyncio
async def test_replay_checkpoint_survives_restart_and_restores_exact_cursor() -> None:
    database = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with database.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(database, expire_on_commit=False)
    session_id = uuid4()
    replay = engine()
    replay.step()
    replay.step()
    async with sessions() as session:
        repository = ReplaySessionRepository(session)
        created = await repository.create(session_id, engine(), checkpointed_at=NOW)
        saved = await repository.save(
            session_id,
            replay.checkpoint(),
            expected_version=created.version,
            checkpointed_at=NOW + timedelta(seconds=1),
        )
        assert saved.version == 1
        await session.commit()
    async with sessions() as session:
        stored = await ReplaySessionRepository(session).load(session_id)
        restarted = engine()
        restarted.restore(stored.checkpoint)
        assert restarted.snapshot() == replay.snapshot()
        assert restarted.step() == replay.step()
        assert await session.scalar(select(func.count()).select_from(ReplaySessionRecord)) == 1
    await database.dispose()


@pytest.mark.asyncio
async def test_replay_persistence_rejects_conflicts_and_stale_updates() -> None:
    database = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with database.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(database, expire_on_commit=False)
    session_id = uuid4()
    async with sessions() as session:
        repository = ReplaySessionRepository(session)
        created = await repository.create(session_id, engine(), checkpointed_at=NOW)
        same = await repository.create(session_id, engine(), checkpointed_at=NOW)
        assert same == created
        with pytest.raises(ValueError, match="conflicting"):
            await repository.create(session_id, engine(3), checkpointed_at=NOW)
        saved = await repository.save(
            session_id,
            engine().checkpoint(),
            expected_version=0,
            checkpointed_at=NOW,
        )
        assert saved.version == 1
        with pytest.raises(ValueError, match="stale"):
            await repository.save(
                session_id,
                engine().checkpoint(),
                expected_version=0,
                checkpointed_at=NOW,
            )
        with pytest.raises(ValueError, match="stale"):
            await repository.save(
                session_id,
                engine(3).checkpoint(),
                expected_version=1,
                checkpointed_at=NOW,
            )
        await session.rollback()
    await database.dispose()
