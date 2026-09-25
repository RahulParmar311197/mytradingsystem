from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database import Base
from packages.domain.models import Candle
from packages.replay import ReplayCoordinator, ReplayEngine, ReplaySessionRepository

NOW = datetime(2026, 9, 24, 4, tzinfo=UTC)
INSTRUMENT_ID = uuid4()


def candles(count: int = 3) -> tuple[Candle, ...]:
    return tuple(
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


class MemoryDatasetLoader:
    def __init__(self, values: tuple[Candle, ...]) -> None:
        self.values = values

    async def load(self, dataset_sha256: str) -> tuple[Candle, ...]:
        return self.values


@pytest.mark.asyncio
async def test_coordinator_steps_seeks_and_recovers_through_persistence() -> None:
    database = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with database.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(database, expire_on_commit=False)
    session_id = uuid4()
    replay = ReplayEngine(candles())
    async with sessions() as session:
        repository = ReplaySessionRepository(session)
        created = await repository.create(session_id, replay, checkpointed_at=NOW)
        coordinator = ReplayCoordinator(repository, MemoryDatasetLoader(candles()))
        stepped = await coordinator.step(
            session_id, expected_version=created.version, checkpointed_at=NOW
        )
        assert stepped.frame is not None and stepped.frame.index == 0
        assert stepped.session.version == 1
        sought = await coordinator.seek(
            session_id,
            as_of=NOW + timedelta(minutes=3),
            expected_version=1,
            checkpointed_at=NOW + timedelta(seconds=1),
        )
        assert sought.checkpoint.next_index == 3
        assert sought.version == 2
        await session.commit()
    async with sessions() as session:
        coordinator = ReplayCoordinator(
            ReplaySessionRepository(session), MemoryDatasetLoader(candles())
        )
        stored, snapshot = await coordinator.snapshot(session_id)
        assert stored.version == 2
        assert snapshot == candles()
        terminal = await coordinator.step(
            session_id, expected_version=2, checkpointed_at=NOW + timedelta(seconds=2)
        )
        assert terminal.frame is None
        assert terminal.session.version == 2
    await database.dispose()


@pytest.mark.asyncio
async def test_coordinator_fails_closed_for_stale_or_changed_evidence() -> None:
    database = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with database.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(database, expire_on_commit=False)
    session_id = uuid4()
    async with sessions() as session:
        repository = ReplaySessionRepository(session)
        await repository.create(session_id, ReplayEngine(candles()), checkpointed_at=NOW)
        valid = ReplayCoordinator(repository, MemoryDatasetLoader(candles()))
        with pytest.raises(ValueError, match="stale"):
            await valid.step(session_id, expected_version=7, checkpointed_at=NOW)
        changed = ReplayCoordinator(repository, MemoryDatasetLoader(candles(2)))
        with pytest.raises(ValueError, match="no longer matches"):
            await changed.snapshot(session_id)
        await session.rollback()
    await database.dispose()
