"""Strict market-data validation which reports, rather than repairs, bad input."""

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from packages.domain.models import Candle, MarketDataQualityEvent


@dataclass(frozen=True, slots=True)
class RawCandle:
    instrument_id: UUID
    timestamp: datetime
    timeframe_seconds: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    source_event_id: str
    open_interest: Decimal | None = None


@dataclass(frozen=True, slots=True)
class ValidationResult:
    accepted: tuple[Candle, ...]
    events: tuple[MarketDataQualityEvent, ...]

    @property
    def is_clean(self) -> bool:
        return not self.events


class CandleValidator:
    def __init__(self, *, maximum_timestamp_drift: timedelta = timedelta(minutes=2)) -> None:
        self.maximum_timestamp_drift = maximum_timestamp_drift

    def validate(
        self, records: Iterable[RawCandle], *, observed_at: datetime | None = None
    ) -> ValidationResult:
        now = (observed_at or datetime.now(UTC)).astimezone(UTC)
        accepted: list[Candle] = []
        events: list[MarketDataQualityEvent] = []
        seen: set[tuple[UUID, datetime, int]] = set()
        previous_by_stream: dict[tuple[UUID, int], datetime] = {}

        for raw in records:
            if raw.timestamp.tzinfo is None or raw.timestamp.utcoffset() is None:
                events.append(self._event(raw, now, "INVALID_TIMESTAMP", "error", {}))
                continue
            timestamp = raw.timestamp.astimezone(UTC)
            identity = (raw.instrument_id, timestamp, raw.timeframe_seconds)
            stream = (raw.instrument_id, raw.timeframe_seconds)
            if identity in seen:
                events.append(self._event(raw, now, "DUPLICATE", "error", {}))
                continue
            seen.add(identity)

            previous = previous_by_stream.get(stream)
            if previous is not None:
                if timestamp < previous:
                    events.append(
                        self._event(
                            raw, now, "OUT_OF_ORDER", "error", {"previous": previous.isoformat()}
                        )
                    )
                    continue
                expected = previous + timedelta(seconds=raw.timeframe_seconds)
                if timestamp > expected:
                    missing = int((timestamp - expected).total_seconds() // raw.timeframe_seconds)
                    events.append(
                        self._event(raw, now, "FEED_GAP", "warning", {"missing": missing})
                    )
            previous_by_stream[stream] = timestamp

            if timestamp > now + self.maximum_timestamp_drift:
                events.append(self._event(raw, now, "TIMESTAMP_DRIFT", "error", {}))
                continue
            try:
                accepted.append(
                    Candle(
                        instrument_id=raw.instrument_id,
                        timestamp=timestamp,
                        timeframe_seconds=raw.timeframe_seconds,
                        open=raw.open,
                        high=raw.high,
                        low=raw.low,
                        close=raw.close,
                        volume=raw.volume,
                        open_interest=raw.open_interest,
                        is_closed=timestamp + timedelta(seconds=raw.timeframe_seconds) <= now,
                    )
                )
            except ValidationError as error:
                events.append(
                    self._event(
                        raw,
                        now,
                        "INVALID_CANDLE",
                        "error",
                        {"errors": json.loads(error.json(include_url=False))},
                    )
                )
        return ValidationResult(tuple(accepted), tuple(events))

    @staticmethod
    def _event(
        raw: RawCandle, observed_at: datetime, code: str, severity: str, details: dict[str, Any]
    ) -> MarketDataQualityEvent:
        return MarketDataQualityEvent(
            instrument_id=raw.instrument_id,
            timestamp=observed_at,
            code=code,
            severity=severity,
            details=details,
            raw_event_id=raw.source_event_id,
        )
