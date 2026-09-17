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
