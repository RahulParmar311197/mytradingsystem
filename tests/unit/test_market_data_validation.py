from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from packages.market_data.validation import CandleValidator, RawCandle


def raw(timestamp: datetime, event_id: str, *, high: str = "101") -> RawCandle:
    return RawCandle(
        instrument_id=INSTRUMENT,
        timestamp=timestamp,
        timeframe_seconds=60,
        open=Decimal("100"),
        high=Decimal(high),
        low=Decimal("99"),
        close=Decimal("100.5"),
        volume=Decimal("10"),
        source_event_id=event_id,
    )


INSTRUMENT = uuid4()
NOW = datetime(2026, 9, 17, 10, tzinfo=UTC)


def test_validation_records_duplicates_gaps_and_bad_ohlc_without_repair() -> None:
    start = NOW - timedelta(minutes=10)
    result = CandleValidator().validate(
        [
            raw(start, "one"),
            raw(start, "duplicate"),
            raw(start + timedelta(minutes=2), "gap"),
            raw(start + timedelta(minutes=3), "bad", high="99"),
        ],
        observed_at=NOW,
    )
    assert len(result.accepted) == 2
    assert [event.code for event in result.events] == ["DUPLICATE", "FEED_GAP", "INVALID_CANDLE"]
    assert result.events[1].details == {"missing": 1}


def test_validation_rejects_naive_and_future_timestamps() -> None:
    result = CandleValidator().validate(
        [raw(NOW.replace(tzinfo=None), "naive"), raw(NOW + timedelta(minutes=3), "future")],
        observed_at=NOW,
    )
    assert not result.accepted
    assert [event.code for event in result.events] == ["INVALID_TIMESTAMP", "TIMESTAMP_DRIFT"]


def test_open_candle_is_visible_but_marked_incomplete() -> None:
    result = CandleValidator().validate([raw(NOW, "current")], observed_at=NOW)
    assert len(result.accepted) == 1
    assert result.accepted[0].is_closed is False
