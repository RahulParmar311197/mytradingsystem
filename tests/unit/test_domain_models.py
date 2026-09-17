from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from packages.domain.models import Candle, Quote


def test_candle_normalizes_timestamp_and_preserves_decimal() -> None:
    candle = Candle(
        instrument_id=uuid4(),
        timestamp=datetime.now(UTC),
        timeframe_seconds=60,
        open=Decimal("100.10"),
        high=Decimal("101.20"),
        low=Decimal("99.95"),
        close=Decimal("100.80"),
        volume=Decimal("500"),
    )
    assert candle.timestamp.tzinfo is UTC
    assert candle.close == Decimal("100.80")


def test_candle_rejects_impossible_prices() -> None:
    with pytest.raises(ValidationError, match="impossible OHLC"):
        Candle(
            instrument_id=uuid4(),
            timestamp=datetime.now(UTC),
            timeframe_seconds=60,
            open=Decimal("100"),
            high=Decimal("99"),
            low=Decimal("98"),
            close=Decimal("100"),
            volume=Decimal("1"),
        )


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        Quote(
            instrument_id=uuid4(),
            timestamp=datetime.now(),
            bid=Decimal("10"),
            ask=Decimal("11"),
            bid_quantity=Decimal("1"),
            ask_quantity=Decimal("1"),
        )


@pytest.mark.parametrize("timestamp", ["2026-09-17T09:15:00", "2026-09-17"])
def test_json_naive_timestamps_cannot_bypass_validation(timestamp: str) -> None:
    import json

    data = {
        "instrument_id": str(uuid4()),
        "timestamp": timestamp,
        "bid": "10",
        "ask": "11",
        "bid_quantity": "1",
        "ask_quantity": "1",
    }
    with pytest.raises(ValidationError, match="timezone-aware"):
        Quote.model_validate_json(json.dumps(data))


def test_json_timestamps_are_normalized_after_parsing() -> None:
    quote = Quote.model_validate(
        {
            "instrument_id": uuid4(),
            "timestamp": "2026-09-17T09:15:00+05:30",
            "bid": "10",
            "ask": "11",
            "bid_quantity": "1",
            "ask_quantity": "1",
        }
    )
    assert quote.timestamp == datetime(2026, 9, 17, 3, 45, tzinfo=UTC)
    assert quote.timestamp.tzinfo is UTC


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_money_is_rejected(value: str) -> None:
    with pytest.raises(ValidationError):
        Quote(
            instrument_id=uuid4(),
            timestamp=datetime.now(UTC),
            bid=value,
            ask="11",
            bid_quantity="1",
            ask_quantity="1",
        )
