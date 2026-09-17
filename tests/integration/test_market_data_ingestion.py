from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database.base import Base
from packages.database.models import CandleRecord, InstrumentRecord, RawCandleRecord
from packages.domain.models import Exchange, Instrument, MarketSegment
from packages.market_data.ingestion import HistoricalCandleIngestor
from packages.market_data.repository import MarketDataRepository
from packages.market_data.validation import CandleValidator, RawCandle


@pytest.mark.asyncio
async def test_ingestion_preserves_raw_and_is_idempotent(tmp_path: object) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    instrument = Instrument(
        id=uuid4(),
        symbol="RELIANCE",
        exchange=Exchange.NSE,
        segment=MarketSegment.CASH,
        tick_size=Decimal("0.05"),
        lot_size=1,
    )
    now = datetime(2026, 9, 17, 10, tzinfo=UTC)
    item = RawCandle(
        instrument_id=instrument.id,
        timestamp=now - timedelta(minutes=2),
        timeframe_seconds=60,
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100.5"),
        volume=Decimal("25"),
        source_event_id="provider-event-1",
    )
    async with sessions() as session:
        repository = MarketDataRepository(session)
        assert await repository.upsert_instruments([instrument]) == 1
        await session.commit()
        ingestor = HistoricalCandleIngestor(repository, CandleValidator())
        first = await ingestor.ingest("sandbox", [item], observed_at=now)
        second = await ingestor.ingest("sandbox", [item], observed_at=now)
        assert (first.raw_inserted, first.normalized_inserted) == (1, 1)
        assert (second.raw_inserted, second.normalized_inserted) == (0, 0)
        assert await session.scalar(select(func.count()).select_from(RawCandleRecord)) == 1
        assert await session.scalar(select(func.count()).select_from(CandleRecord)) == 1
        assert await session.scalar(select(func.count()).select_from(InstrumentRecord)) == 1
    await engine.dispose()
