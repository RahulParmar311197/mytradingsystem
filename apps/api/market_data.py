"""Authenticated historical market data with explicit point-in-time availability."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import or_, select

from packages.auth import Principal
from packages.database import Database
from packages.database.models import (
    CandleRecord,
    InstrumentRecord,
    MarketDataQualityEventRecord,
    RawCandleRecord,
)
from packages.domain.models import Candle, Instrument
from packages.market_data.aggregation import (
    Timeframe,
    aggregate_closed_candles,
    candle_available_at,
)
from packages.market_data.ingestion import HistoricalCandleIngestor
from packages.market_data.repository import MarketDataRepository
from packages.market_data.validation import CandleValidator, RawCandle


class RawCandleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instrument_id: UUID
    timestamp: datetime
    timeframe_seconds: int = Field(ge=60, le=86400)
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    source_event_id: str = Field(min_length=1, max_length=128)
    open_interest: Decimal | None = None

    @field_validator("timestamp")
    @classmethod
    def require_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        return value.astimezone(UTC)


class HistoricalIngestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(min_length=1, max_length=32)
    candles: list[RawCandleInput] = Field(min_length=1, max_length=1000)


class InstrumentImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instruments: list[Instrument] = Field(min_length=1, max_length=500)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "timestamps must include a timezone"
        )
    return value.astimezone(UTC)


def _from_database(value: datetime) -> datetime:
    # SQLite drops timezone information; all stored market timestamps are UTC.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _raw_identity(item: RawCandleInput) -> tuple[object, ...]:
    return (
        item.instrument_id,
        item.timestamp,
        item.timeframe_seconds,
        item.open,
        item.high,
        item.low,
        item.close,
        item.volume,
        item.open_interest,
    )


def create_market_data_router(
    database: Database, authenticated_principal: object, operator_principal: object
) -> APIRouter:
    router = APIRouter(tags=["market-data"])

    @router.post("/api/v1/operator/instruments", status_code=status.HTTP_201_CREATED)
    async def import_instruments(
        payload: InstrumentImportRequest,
        _: Annotated[Principal, Depends(operator_principal)],
    ) -> dict[str, int]:
        async with database.sessions() as session:
            repository = MarketDataRepository(session)
            identities: dict[tuple[str, str, str], Instrument] = {}
            for instrument in payload.instruments:
                key = (instrument.exchange.value, instrument.segment.value, instrument.symbol)
                if key in identities and identities[key] != instrument:
                    raise HTTPException(status.HTTP_409_CONFLICT, "conflicting instrument mapping")
                identities[key] = instrument
            existing = (
                await session.scalars(
                    select(InstrumentRecord).where(
                        or_(
                            InstrumentRecord.symbol.in_(
                                {item.symbol for item in payload.instruments}
                            ),
                            InstrumentRecord.id.in_({item.id for item in payload.instruments}),
                        )
                    )
                )
            ).all()
            for row in existing:
                key = (row.exchange, row.segment, row.symbol)
                if key in identities and (
                    row.id != identities[key].id
                    or row.tick_size != identities[key].tick_size
                    or row.lot_size != identities[key].lot_size
                    or row.isin != identities[key].isin
                    or row.currency != identities[key].currency
                ):
                    raise HTTPException(status.HTTP_409_CONFLICT, "conflicting instrument mapping")
                if any(
                    item.id == row.id
                    and (item.exchange.value, item.segment.value, item.symbol) != key
                    for item in payload.instruments
                ):
                    raise HTTPException(status.HTTP_409_CONFLICT, "conflicting instrument mapping")
            inserted = await repository.upsert_instruments(payload.instruments)
            await session.commit()
        return {"inserted": inserted}

    @router.get("/api/v1/instruments")
    async def list_instruments(
        _: Annotated[Principal, Depends(authenticated_principal)],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, object]:
        async with database.sessions() as session:
            records = (
                await session.scalars(
                    select(InstrumentRecord)
                    .order_by(
                        InstrumentRecord.exchange, InstrumentRecord.segment, InstrumentRecord.symbol
                    )
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
        items = [
            Instrument(
                id=row.id,
                symbol=row.symbol,
                exchange=row.exchange,
                segment=row.segment,
                isin=row.isin,
                tick_size=row.tick_size,
                lot_size=row.lot_size,
                currency=row.currency,
                active=row.active,
            )
            for row in records
        ]
        return {"items": items, "limit": limit, "offset": offset}

    @router.post("/api/v1/operator/market-data/candles", status_code=status.HTTP_201_CREATED)
    async def ingest_candles(
        payload: HistoricalIngestionRequest,
        _: Annotated[Principal, Depends(operator_principal)],
    ) -> dict[str, int]:
        instrument_ids = {item.instrument_id for item in payload.candles}
        async with database.sessions() as session:
            known = set(
                (
                    await session.scalars(
                        select(InstrumentRecord.id).where(InstrumentRecord.id.in_(instrument_ids))
                    )
                ).all()
            )
            if known != instrument_ids:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown instrument ID")
            by_event: dict[str, RawCandleInput] = {}
            for item in payload.candles:
                prior = by_event.get(item.source_event_id)
                if prior is not None and _raw_identity(prior) != _raw_identity(item):
                    raise HTTPException(status.HTTP_409_CONFLICT, "source event ID changed payload")
                by_event[item.source_event_id] = item
            previous = (
                await session.scalars(
                    select(RawCandleRecord).where(
                        RawCandleRecord.source == payload.source,
                        RawCandleRecord.source_event_id.in_(by_event),
                    )
                )
            ).all()
            for row in previous:
                item = by_event[row.source_event_id]
                stored = row.payload
                prior_identity = (
                    row.instrument_id,
                    _from_database(row.event_timestamp),
                    row.timeframe_seconds,
                    *(
                        Decimal(stored[field])
                        for field in ("open", "high", "low", "close", "volume")
                    ),
                    Decimal(stored["open_interest"])
                    if stored["open_interest"] is not None
                    else None,
                )
                if prior_identity != _raw_identity(item):
                    raise HTTPException(status.HTTP_409_CONFLICT, "source event ID changed payload")
            records = [RawCandle(**item.model_dump()) for item in payload.candles]
            result = await HistoricalCandleIngestor(
                MarketDataRepository(session), CandleValidator()
            ).ingest(payload.source, records, observed_at=datetime.now(UTC))
        return {
            "raw_inserted": result.raw_inserted,
            "normalized_inserted": result.normalized_inserted,
            "quality_events_recorded": result.quality_events_recorded,
        }

    @router.get("/api/v1/instruments/{instrument_id}/candles")
    async def list_candles(
        instrument_id: UUID,
        _: Annotated[Principal, Depends(authenticated_principal)],
        start: datetime,
        end: datetime,
        as_of: datetime,
        timeframe_seconds: Annotated[int, Query(ge=60, le=86400)] = 60,
        aggregate_seconds: Timeframe | None = None,
        limit: Annotated[int, Query(ge=1, le=1000)] = 500,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, object]:
        from_at, to_at, cutoff = _utc(start), _utc(end), _utc(as_of)
        if from_at >= to_at or to_at - from_at > timedelta(days=31):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "range must span at most 31 days"
            )
        if aggregate_seconds is not None and int(aggregate_seconds) <= timeframe_seconds:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "aggregate must exceed source timeframe"
            )
        async with database.sessions() as session:
            if await session.get(InstrumentRecord, instrument_id) is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "instrument not found")
            rows = (
                await session.scalars(
                    select(CandleRecord)
                    .where(
                        CandleRecord.instrument_id == instrument_id,
                        CandleRecord.timeframe_seconds == timeframe_seconds,
                        CandleRecord.event_timestamp >= from_at,
                        CandleRecord.event_timestamp < to_at,
                        CandleRecord.event_timestamp <= cutoff,
                        CandleRecord.is_closed.is_(True),
                    )
                    .order_by(CandleRecord.event_timestamp)
                    .limit(50000)
                )
            ).all()
        candles = tuple(
            Candle(
                instrument_id=row.instrument_id,
                timestamp=_from_database(row.event_timestamp),
                timeframe_seconds=row.timeframe_seconds,
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                volume=row.volume,
                open_interest=row.open_interest,
                is_closed=row.is_closed,
            )
            for row in rows
        )
        if aggregate_seconds is not None:
            try:
                candles = aggregate_closed_candles(candles, aggregate_seconds, as_of=cutoff)
            except ValueError as error:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
        else:
            candles = tuple(c for c in candles if candle_available_at(c) <= cutoff)
        return {
            "items": candles[offset : offset + limit],
            "limit": limit,
            "offset": offset,
            "as_of": cutoff,
            "data_type": "historical",
        }

    @router.get("/api/v1/instruments/{instrument_id}/quality-events")
    async def list_quality_events(
        instrument_id: UUID,
        _: Annotated[Principal, Depends(authenticated_principal)],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, object]:
        async with database.sessions() as session:
            if await session.get(InstrumentRecord, instrument_id) is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "instrument not found")
            rows = (
                await session.scalars(
                    select(MarketDataQualityEventRecord)
                    .where(MarketDataQualityEventRecord.instrument_id == instrument_id)
                    .order_by(
                        MarketDataQualityEventRecord.event_timestamp,
                        MarketDataQualityEventRecord.id,
                    )
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
        return {
            "items": [
                {
                    "code": row.code,
                    "severity": row.severity,
                    "details": row.details,
                    "raw_event_id": row.raw_event_id,
                    "timestamp": _from_database(row.event_timestamp),
                }
                for row in rows
            ],
            "limit": limit,
            "offset": offset,
        }

    return router
