from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database.base import Base
from packages.database.models import InstrumentRecord, RawOptionChainRecord
from packages.domain.models import (
    Exchange,
    Instrument,
    MarketSegment,
    OptionChain,
    OptionChainEntry,
    OptionContract,
    OptionType,
    Quote,
)
from packages.options import OptionChainSnapshotRepository

NOW = datetime(2026, 9, 19, 5, tzinfo=UTC)
EXPIRY = date(2026, 9, 24)


def option_chain(underlying_id: UUID, timestamp: datetime, open_interest: str) -> OptionChain:
    instrument = Instrument(
        symbol="NIFTY-20260924-25000-CE",
        exchange=Exchange.NSE,
        segment=MarketSegment.OPTIONS,
        tick_size=Decimal("0.05"),
        lot_size=25,
    )
    return OptionChain(
        underlying_id=underlying_id,
        expiry=EXPIRY,
        timestamp=timestamp,
        entries=(
            OptionChainEntry(
                contract=OptionContract(
                    instrument=instrument,
                    underlying_id=underlying_id,
                    expiry=EXPIRY,
                    strike=Decimal(25000),
                    option_type=OptionType.CALL,
                ),
                quote=Quote(
                    instrument_id=instrument.id,
                    timestamp=timestamp,
                    bid=Decimal(100),
                    ask=Decimal("100.05"),
                    bid_quantity=Decimal(100),
                    ask_quantity=Decimal(100),
                ),
                open_interest=Decimal(open_interest),
                change_in_open_interest=Decimal(0),
                volume=Decimal(1000),
            ),
        ),
    )


@pytest.mark.asyncio
async def test_chain_snapshots_are_idempotent_and_point_in_time() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    underlying_id = uuid4()
    first = option_chain(underlying_id, NOW, "100")
    second = option_chain(underlying_id, NOW + timedelta(minutes=1), "200")
    async with sessions() as session:
        session.add(
            InstrumentRecord(
                id=underlying_id,
                symbol="NIFTY",
                exchange="NSE",
                segment="INDEX",
                tick_size=Decimal("0.05"),
                lot_size=1,
                currency="INR",
                active=True,
            )
        )
        await session.flush()
        repository = OptionChainSnapshotRepository(session)
        await repository.ingest(
            first,
            source="sandbox",
            source_event_id="chain-1",
            raw_payload={"provider": "first"},
        )
        duplicate = await repository.ingest(
            first,
            source="sandbox",
            source_event_id="chain-1",
            raw_payload={"provider": "first"},
        )
        assert duplicate == first
        await repository.ingest(
            second,
            source="sandbox",
            source_event_id="chain-2",
            raw_payload={"provider": "second"},
        )
        await session.commit()

    async with sessions() as session:
        repository = OptionChainSnapshotRepository(session)
        recovered = await repository.latest_as_of(underlying_id, EXPIRY, NOW)
        assert recovered == first
        assert await session.scalar(select(func.count()).select_from(RawOptionChainRecord)) == 2
        with pytest.raises(ValueError, match="different content"):
            await repository.ingest(
                second,
                source="sandbox",
                source_event_id="chain-1",
                raw_payload={"provider": "changed"},
            )
    await engine.dispose()
