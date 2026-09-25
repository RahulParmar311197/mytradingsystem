from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from packages.domain.models import Candle, Exchange, MarketSession
from packages.market_data.aggregation import Timeframe, aggregate_closed_candles

INDIA = ZoneInfo("Asia/Kolkata")
INSTRUMENT = uuid4()


def minute_candles(count: int, start: datetime | None = None) -> list[Candle]:
    session_open = start or datetime(2026, 9, 17, 9, 15, tzinfo=INDIA)
    return [
        Candle(
            instrument_id=INSTRUMENT,
            timestamp=(session_open + timedelta(minutes=index)).astimezone(UTC),
            timeframe_seconds=60,
            open=Decimal(100 + index),
            high=Decimal(101 + index),
            low=Decimal(99 + index),
            close=Decimal("100.5") + index,
            volume=Decimal(10),
            is_closed=True,
        )
        for index in range(count)
    ]


def test_five_minute_boundary_aligns_to_nse_open() -> None:
    candles = minute_candles(5)
    result = aggregate_closed_candles(
        candles, Timeframe.MINUTE_5, as_of=datetime(2026, 9, 17, 9, 20, tzinfo=INDIA)
    )
    assert len(result) == 1
    assert result[0].timestamp == datetime(2026, 9, 17, 9, 15, tzinfo=INDIA).astimezone(UTC)
    assert result[0].open == Decimal("100")
    assert result[0].close == Decimal("104.5")
    assert result[0].volume == Decimal("50")


def test_incomplete_bucket_is_not_exposed_and_has_no_lookahead() -> None:
    candles = minute_candles(5)
    before_close = aggregate_closed_candles(
        candles, Timeframe.MINUTE_5, as_of=datetime(2026, 9, 17, 9, 19, 59, tzinfo=INDIA)
    )
    assert before_close == ()
    missing_input = aggregate_closed_candles(
        candles[:3] + candles[4:],
        Timeframe.MINUTE_5,
        as_of=datetime(2026, 9, 17, 9, 21, tzinfo=INDIA),
    )
    assert missing_input == ()


def test_session_filter_prevents_previous_or_after_hours_data_entering_bucket() -> None:
    regular = minute_candles(5)
    before_open = minute_candles(1, datetime(2026, 9, 17, 9, 14, tzinfo=INDIA))
    result = aggregate_closed_candles(
        before_open + regular,
        Timeframe.MINUTE_5,
        as_of=datetime(2026, 9, 17, 9, 20, tzinfo=INDIA),
    )
    assert len(result) == 1
    assert result[0].open == regular[0].open


def test_daily_candle_requires_complete_375_minute_session() -> None:
    candles = minute_candles(375)
    assert (
        aggregate_closed_candles(
            candles[:-1], Timeframe.DAY_1, as_of=datetime(2026, 9, 17, 16, tzinfo=INDIA)
        )
        == ()
    )
    complete = aggregate_closed_candles(
        candles, Timeframe.DAY_1, as_of=datetime(2026, 9, 17, 15, 30, tzinfo=INDIA)
    )
    assert len(complete) == 1
    assert complete[0].volume == Decimal("3750")


def test_four_hour_session_close_emits_closed_truncated_final_bucket() -> None:
    candles = minute_candles(375)
    complete = aggregate_closed_candles(
        candles, Timeframe.HOUR_4, as_of=datetime(2026, 9, 17, 15, 30, tzinfo=INDIA)
    )
    assert len(complete) == 2
    assert complete[0].timestamp.astimezone(INDIA).time().isoformat() == "09:15:00"
    assert complete[1].timestamp.astimezone(INDIA).time().isoformat() == "13:15:00"
    assert complete[1].volume == Decimal("1350")


def test_weekly_candle_is_unavailable_until_friday_close() -> None:
    daily = [
        Candle(
            instrument_id=INSTRUMENT,
            timestamp=datetime(2026, 9, 14 + day, 9, 15, tzinfo=INDIA).astimezone(UTC),
            timeframe_seconds=Timeframe.DAY_1,
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=Decimal("10"),
            is_closed=True,
        )
        for day in range(5)
    ]
    assert (
        aggregate_closed_candles(
            daily, Timeframe.WEEK_1, as_of=datetime(2026, 9, 18, 15, 29, tzinfo=INDIA)
        )
        == ()
    )
    result = aggregate_closed_candles(
        daily, Timeframe.WEEK_1, as_of=datetime(2026, 9, 18, 15, 30, tzinfo=INDIA)
    )
    assert len(result) == 1


def test_verified_holiday_week_closes_on_last_trading_session() -> None:
    monday = datetime(2026, 9, 14, 9, 15, tzinfo=INDIA)
    sessions = tuple(
        MarketSession(
            exchange=Exchange.NSE,
            session_date=(monday + timedelta(days=day)).date(),
            opens_at=monday + timedelta(days=day),
            closes_at=monday + timedelta(days=day, hours=6, minutes=15),
            is_trading_day=day != 4,
        )
        for day in range(5)
    )
    candles = [
        Candle(
            instrument_id=INSTRUMENT,
            timestamp=sessions[day].opens_at,
            timeframe_seconds=Timeframe.DAY_1,
            open=Decimal(100),
            high=Decimal(102),
            low=Decimal(99),
            close=Decimal(101),
            volume=Decimal(10),
            is_closed=True,
        )
        for day in range(4)
    ]
    before = aggregate_closed_candles(
        candles,
        Timeframe.WEEK_1,
        as_of=sessions[3].closes_at - timedelta(seconds=1),
        sessions=sessions,
    )
    assert before == ()
    complete = aggregate_closed_candles(
        candles,
        Timeframe.WEEK_1,
        as_of=sessions[3].closes_at,
        sessions=sessions,
    )
    assert len(complete) == 1
    assert complete[0].volume == Decimal(40)
    with pytest.raises(ValueError, match="all five weekdays"):
        aggregate_closed_candles(
            candles,
            Timeframe.WEEK_1,
            as_of=sessions[3].closes_at,
            sessions=sessions[:4],
        )
