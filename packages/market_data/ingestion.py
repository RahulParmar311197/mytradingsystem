from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from packages.domain.models import MarketDataQualityEvent
from packages.market_data.repository import MarketDataRepository
from packages.market_data.validation import CandleValidator, RawCandle


@dataclass(frozen=True, slots=True)
class IngestionResult:
    raw_inserted: int
    normalized_inserted: int
    quality_events_recorded: int


class HistoricalCandleIngestor:
    def __init__(self, repository: MarketDataRepository, validator: CandleValidator) -> None:
        self.repository = repository
        self.validator = validator

    async def ingest(
        self, source: str, records: Sequence[RawCandle], *, observed_at: datetime
    ) -> IngestionResult:
        """Persist raw input, quality events, and valid normalized rows atomically."""
        validation = self.validator.validate(records, observed_at=observed_at)
        existing = await self.repository.existing_candles(validation.accepted)
        source_ids = {
            (
                raw.instrument_id,
                raw.timestamp.astimezone(UTC),
                raw.timeframe_seconds,
            ): raw.source_event_id
            for raw in records
            if raw.timestamp.tzinfo is not None and raw.timestamp.utcoffset() is not None
        }
        conflicts: list[MarketDataQualityEvent] = []
        new_candles = []
        for item in validation.accepted:
            key = (item.instrument_id, item.timestamp, item.timeframe_seconds)
            previous = existing.get(key)
            if previous is None:
                new_candles.append(item)
            elif previous != item:
                conflicts.append(
                    MarketDataQualityEvent(
                        instrument_id=item.instrument_id,
                        timestamp=observed_at,
                        code="CONFLICTING_CANDLE",
                        severity="error",
                        details={
                            "timestamp": item.timestamp.isoformat(),
                            "timeframe_seconds": item.timeframe_seconds,
                        },
                        raw_event_id=source_ids[key],
                    )
                )
        raw_count = await self.repository.store_raw(source, records)
        normalized_count = await self.repository.store_candles(new_candles)
        event_count = await self.repository.store_quality_events((*validation.events, *conflicts))
        await self.repository.session.commit()
        return IngestionResult(raw_count, normalized_count, event_count)
