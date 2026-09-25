from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models import (
    CandleRecord,
    InstrumentRecord,
    MarketDataQualityEventRecord,
    RawCandleRecord,
)
from packages.domain.models import Candle, Instrument, MarketDataQualityEvent
from packages.market_data.validation import RawCandle


class MarketDataRepository:
    """Idempotent raw/normalized persistence for supported SQL dialects."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def existing_candles(
        self, candles: Sequence[Candle]
    ) -> dict[tuple[UUID, datetime, int], Candle]:
        """Read possible identity collisions before inserting a normalized batch."""
        if not candles:
            return {}
        rows = (
            await self.session.scalars(
                select(CandleRecord).where(
                    CandleRecord.instrument_id.in_({item.instrument_id for item in candles}),
                    CandleRecord.event_timestamp.in_({item.timestamp for item in candles}),
                    CandleRecord.timeframe_seconds.in_(
                        {item.timeframe_seconds for item in candles}
                    ),
                )
            )
        ).all()
        result: dict[tuple[UUID, datetime, int], Candle] = {}
        for row in rows:
            timestamp = row.event_timestamp
            timestamp = (
                timestamp.replace(tzinfo=UTC)
                if timestamp.tzinfo is None
                else timestamp.astimezone(UTC)
            )
            candle = Candle(
                instrument_id=row.instrument_id,
                timestamp=timestamp,
                timeframe_seconds=row.timeframe_seconds,
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                volume=row.volume,
                open_interest=row.open_interest,
                is_closed=row.is_closed,
            )
            result[(candle.instrument_id, candle.timestamp, candle.timeframe_seconds)] = candle
        return result

    async def upsert_instruments(self, instruments: Sequence[Instrument]) -> int:
        rows = [
            {
                "id": item.id,
                "symbol": item.symbol,
                "exchange": item.exchange.value,
                "segment": item.segment.value,
                "isin": item.isin,
                "tick_size": item.tick_size,
                "lot_size": item.lot_size,
                "currency": item.currency,
                "active": item.active,
            }
            for item in instruments
        ]
        return await self._insert_ignore(InstrumentRecord, rows, ["exchange", "segment", "symbol"])

    async def store_raw(self, source: str, records: Sequence[RawCandle]) -> int:
        rows = [
            {
                "source": source,
                "source_event_id": item.source_event_id,
                "instrument_id": item.instrument_id,
                "event_timestamp": item.timestamp,
                "timeframe_seconds": item.timeframe_seconds,
                "payload": {
                    "open": str(item.open),
                    "high": str(item.high),
                    "low": str(item.low),
                    "close": str(item.close),
                    "volume": str(item.volume),
                    "open_interest": str(item.open_interest)
                    if item.open_interest is not None
                    else None,
                },
            }
            for item in records
        ]
        return await self._insert_ignore(RawCandleRecord, rows, ["source", "source_event_id"])

    async def store_candles(self, candles: Sequence[Candle]) -> int:
        rows = [
            {
                "instrument_id": item.instrument_id,
                "event_timestamp": item.timestamp,
                "timeframe_seconds": item.timeframe_seconds,
                "open": item.open,
                "high": item.high,
                "low": item.low,
                "close": item.close,
                "volume": item.volume,
                "open_interest": item.open_interest,
                "is_closed": item.is_closed,
            }
            for item in candles
        ]
        return await self._insert_ignore(
            CandleRecord, rows, ["instrument_id", "event_timestamp", "timeframe_seconds"]
        )

    async def store_quality_events(self, events: Sequence[MarketDataQualityEvent]) -> int:
        rows = [
            {
                "id": item.id,
                "instrument_id": item.instrument_id,
                "event_timestamp": item.timestamp,
                "code": item.code,
                "severity": item.severity,
                "details": item.details,
                "raw_event_id": item.raw_event_id,
            }
            for item in events
        ]
        return await self._insert_ignore(
            MarketDataQualityEventRecord, rows, ["raw_event_id", "code"]
        )

    async def _insert_ignore(
        self, model: type[Any], rows: list[dict[str, Any]], conflict_columns: list[str]
    ) -> int:
        if not rows:
            return 0
        dialect = self.session.get_bind().dialect.name
        statement: Any
        if dialect == "postgresql":
            statement = (
                postgres_insert(model)
                .values(rows)
                .on_conflict_do_nothing(index_elements=conflict_columns)
            )
        elif dialect == "sqlite":
            statement = (
                sqlite_insert(model)
                .values(rows)
                .on_conflict_do_nothing(index_elements=conflict_columns)
            )
        else:
            raise RuntimeError(f"unsupported database dialect for idempotent ingestion: {dialect}")
        result = await self.session.execute(statement)
        rowcount = getattr(result, "rowcount", 0)
        return max(int(rowcount or 0), 0)
