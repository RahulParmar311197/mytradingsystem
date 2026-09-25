"""Content-addressed replay datasets with integrity verification on every load."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models import ReplayDatasetRecord
from packages.domain.models import Candle
from packages.replay.engine import ReplayEngine


@dataclass(frozen=True, slots=True)
class StoredReplayDataset:
    dataset_sha256: str
    instrument_id: UUID
    timeframe_seconds: int
    total_events: int
    first_timestamp: datetime
    last_timestamp: datetime
    created_at: datetime


class ReplayDatasetRepository:
    """Persist immutable candle streams and implement the replay loader boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def store(
        self, candles: tuple[Candle, ...], *, created_at: datetime
    ) -> StoredReplayDataset:
        created_at = _utc(created_at)
        engine = ReplayEngine(candles)
        existing = await self.session.get(ReplayDatasetRecord, engine.dataset_sha256)
        if existing is not None:
            loaded = _validated_candles(existing)
            if loaded != candles:
                raise ValueError("replay dataset digest has conflicting content")
            return _stored(existing)
        record = ReplayDatasetRecord(
            dataset_sha256=engine.dataset_sha256,
            instrument_id=engine.instrument_id,
            timeframe_seconds=engine.timeframe_seconds,
            total_events=engine.total,
            first_timestamp=candles[0].timestamp,
            last_timestamp=candles[-1].timestamp,
            candles=[candle.model_dump(mode="json") for candle in candles],
            created_at=created_at,
        )
        self.session.add(record)
        await self.session.flush()
        return _stored(record)

    async def load(self, dataset_sha256: str) -> tuple[Candle, ...]:
        if len(dataset_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in dataset_sha256
        ):
            raise ValueError("replay dataset digest must be lowercase SHA-256")
        record = await self.session.get(ReplayDatasetRecord, dataset_sha256)
        if record is None:
            raise KeyError("replay dataset does not exist")
        return _validated_candles(record)

    async def list_recent(
        self, *, limit: int = 25, offset: int = 0
    ) -> tuple[StoredReplayDataset, ...]:
        _validate_page(limit, offset)
        records = (
            await self.session.scalars(
                select(ReplayDatasetRecord)
                .order_by(
                    ReplayDatasetRecord.created_at.desc(),
                    ReplayDatasetRecord.dataset_sha256.asc(),
                )
                .offset(offset)
                .limit(limit)
            )
        ).all()
        for record in records:
            _validated_candles(record)
        return tuple(_stored(record) for record in records)


def _validated_candles(record: ReplayDatasetRecord) -> tuple[Candle, ...]:
    try:
        candles = tuple(Candle.model_validate(item) for item in record.candles)
        engine = ReplayEngine(candles)
    except (TypeError, ValueError) as error:
        raise ValueError("stored replay dataset payload is invalid") from error
    if (
        engine.dataset_sha256 != record.dataset_sha256
        or engine.instrument_id != record.instrument_id
        or engine.timeframe_seconds != record.timeframe_seconds
        or engine.total != record.total_events
        or candles[0].timestamp != _utc(record.first_timestamp)
        or candles[-1].timestamp != _utc(record.last_timestamp)
    ):
        raise ValueError("stored replay dataset failed integrity verification")
    return candles


def _stored(record: ReplayDatasetRecord) -> StoredReplayDataset:
    return StoredReplayDataset(
        record.dataset_sha256,
        record.instrument_id,
        record.timeframe_seconds,
        record.total_events,
        _utc(record.first_timestamp),
        _utc(record.last_timestamp),
        _utc(record.created_at),
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _validate_page(limit: int, offset: int) -> None:
    if not 1 <= limit <= 100 or offset < 0:
        raise ValueError("replay page requires limit 1..100 and non-negative offset")
