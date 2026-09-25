from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database.base import Base
from packages.database.models import InstrumentRecord
from packages.options import OptionIVHistoryRepository


@pytest.mark.asyncio
async def test_iv_history_is_idempotent_point_in_time_and_restart_safe() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    instrument_id = uuid4()
    now = datetime(2026, 9, 19, 5, tzinfo=UTC)
    async with sessions() as session:
        session.add(
            InstrumentRecord(
                id=instrument_id,
                symbol="NIFTY-20260924-25000-CE",
                exchange="NSE",
                segment="OPTIONS",
                tick_size=Decimal("0.05"),
                lot_size=25,
                currency="INR",
                active=True,
            )
        )
        await session.flush()
        repository = OptionIVHistoryRepository(session)
        for index, value in enumerate(("0.20", "0.21", "0.22")):
            await repository.ingest(
                instrument_id=instrument_id,
                observed_at=now + timedelta(minutes=index),
                implied_volatility=Decimal(value),
                source="sandbox",
                source_event_id=f"iv-{index}",
            )
        duplicate = await repository.ingest(
            instrument_id=instrument_id,
            observed_at=now,
            implied_volatility=Decimal("0.20"),
            source="sandbox",
            source_event_id="iv-0",
        )
        assert duplicate.implied_volatility == Decimal("0.20")
        await session.commit()

    async with sessions() as session:
        recovered = await OptionIVHistoryRepository(session).history_as_of(
            instrument_id, now + timedelta(minutes=1)
        )
        assert tuple(item.implied_volatility for item in recovered) == (
            Decimal("0.2000000000"),
            Decimal("0.2100000000"),
        )
        with pytest.raises(ValueError, match="different content"):
            await OptionIVHistoryRepository(session).ingest(
                instrument_id=instrument_id,
                observed_at=now,
                implied_volatility=Decimal("0.30"),
                source="sandbox",
                source_event_id="iv-0",
            )
    await engine.dispose()
