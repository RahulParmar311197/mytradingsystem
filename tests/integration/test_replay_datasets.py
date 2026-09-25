from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database import Base
from packages.database.models import ReplayDatasetRecord
from packages.domain.models import Candle
from packages.replay import ReplayDatasetRepository, ReplayEngine

NOW = datetime(2026, 9, 24, 5, tzinfo=UTC)
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
            volume=Decimal(1000 + index),
        )
        for index in range(count)
    )


@pytest.mark.asyncio
async def test_replay_dataset_is_idempotent_and_survives_restart() -> None:
    database = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with database.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(database, expire_on_commit=False)
    stream = candles()
    digest = ReplayEngine(stream).dataset_sha256
    async with sessions() as session:
        repository = ReplayDatasetRepository(session)
        first = await repository.store(stream, created_at=NOW)
        repeated = await repository.store(stream, created_at=NOW + timedelta(hours=1))
        assert first == repeated
        assert first.dataset_sha256 == digest
        await session.commit()
    async with sessions() as session:
        loaded = await ReplayDatasetRepository(session).load(digest)
        assert loaded == stream
        assert ReplayEngine(loaded).dataset_sha256 == digest
    await database.dispose()


@pytest.mark.asyncio
async def test_replay_dataset_fails_closed_on_tampered_payload_or_bad_digest() -> None:
    database = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with database.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(database, expire_on_commit=False)
    stream = candles()
    digest = ReplayEngine(stream).dataset_sha256
    async with sessions() as session:
        repository = ReplayDatasetRepository(session)
        await repository.store(stream, created_at=NOW)
        await session.commit()
    async with sessions() as session:
        record = await session.get(ReplayDatasetRecord, digest)
        assert record is not None
        record.total_events += 1
        await session.commit()
    async with sessions() as session:
        repository = ReplayDatasetRepository(session)
        with pytest.raises(ValueError, match="integrity"):
            await repository.load(digest)
        with pytest.raises(ValueError, match="lowercase SHA-256"):
            await repository.load("NOT-A-DIGEST")
        with pytest.raises(KeyError, match="does not exist"):
            await repository.load("0" * 64)
    await database.dispose()


@pytest.mark.asyncio
async def test_replay_dataset_discovery_is_bounded_ordered_and_integrity_checked() -> None:
    database = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with database.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(database, expire_on_commit=False)
    async with sessions() as session:
        repository = ReplayDatasetRepository(session)
        older = await repository.store(candles(2), created_at=NOW)
        newer = await repository.store(candles(3), created_at=NOW + timedelta(seconds=1))
        await session.commit()
    async with sessions() as session:
        repository = ReplayDatasetRepository(session)
        assert await repository.list_recent(limit=1) == (newer,)
        assert await repository.list_recent(limit=1, offset=1) == (older,)
        with pytest.raises(ValueError, match=r"limit 1\.\.100"):
            await repository.list_recent(limit=101)
    await database.dispose()
