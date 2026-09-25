from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database import Base
from packages.domain.models import Candle
from packages.replay import (
    ReplayCoordinator,
    ReplayEngine,
    ReplayScheduleOutcome,
    ReplayScheduler,
    ReplaySessionRepository,
)

NOW = datetime(2026, 9, 24, 10, tzinfo=UTC)
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
    async def load(self, dataset_sha256: str) -> tuple[Candle, ...]:
        return candles()


@pytest.mark.asyncio
async def test_scheduler_serializes_committed_steps_at_bounded_rate() -> None:
    database = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with database.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(database, expire_on_commit=False)
    session_id = uuid4()
    delays: list[float] = []

    async def record_delay(seconds: float) -> None:
        delays.append(seconds)

    async with sessions() as session:
        repository = ReplaySessionRepository(session)
        await repository.create(session_id, ReplayEngine(candles()), checkpointed_at=NOW)
        await session.commit()
        scheduler = ReplayScheduler(
            ReplayCoordinator(repository, MemoryDatasetLoader()),
            commit=session.commit,
            sleep=record_delay,
            now=lambda: NOW + timedelta(seconds=1),
        )
        result = await scheduler.run(
            session_id, expected_version=0, candles_per_second=2, maximum_steps=3
        )
        assert result.outcome is ReplayScheduleOutcome.COMPLETE
        assert result.frames_emitted == 3
        assert result.session.version == 3
        assert delays == [0.5, 0.5]
    async with sessions() as session:
        recovered = await ReplaySessionRepository(session).load(session_id)
        assert recovered.version == recovered.checkpoint.next_index == 3
    await database.dispose()


@pytest.mark.asyncio
async def test_scheduler_stops_cleanly_and_validates_bounds() -> None:
    database = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with database.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(database, expire_on_commit=False)
    session_id = uuid4()
    stop = False

    async def request_stop(_: float) -> None:
        nonlocal stop
        stop = True

    async with sessions() as session:
        repository = ReplaySessionRepository(session)
        await repository.create(session_id, ReplayEngine(candles()), checkpointed_at=NOW)
        await session.commit()
        scheduler = ReplayScheduler(
            ReplayCoordinator(repository, MemoryDatasetLoader()),
            commit=session.commit,
            sleep=request_stop,
            now=lambda: NOW,
        )
        result = await scheduler.run(
            session_id, expected_version=0, maximum_steps=3, should_stop=lambda: stop
        )
        assert result.outcome is ReplayScheduleOutcome.STOPPED
        assert result.frames_emitted == 1
        with pytest.raises(ValueError, match="rate"):
            await scheduler.run(session_id, expected_version=1, candles_per_second=0)
        with pytest.raises(ValueError, match="maximum steps"):
            await scheduler.run(session_id, expected_version=1, maximum_steps=0)
    await database.dispose()
