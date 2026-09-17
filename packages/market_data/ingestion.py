from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

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
        raw_count = await self.repository.store_raw(source, records)
        normalized_count = await self.repository.store_candles(validation.accepted)
        event_count = await self.repository.store_quality_events(validation.events)
        await self.repository.session.commit()
        return IngestionResult(raw_count, normalized_count, event_count)
