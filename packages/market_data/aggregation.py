"""Point-in-time candle aggregation aligned to the NSE regular session."""

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from enum import IntEnum
from itertools import pairwise
from zoneinfo import ZoneInfo

from packages.domain.models import Candle, Exchange, MarketSession

INDIA = ZoneInfo("Asia/Kolkata")
NSE_OPEN = time(9, 15)
NSE_CLOSE = time(15, 30)


class Timeframe(IntEnum):
    MINUTE_1 = 60
    MINUTE_3 = 180
    MINUTE_5 = 300
    MINUTE_15 = 900
    MINUTE_30 = 1800
    HOUR_1 = 3600
    HOUR_4 = 14400
    DAY_1 = 86400
    WEEK_1 = 604800


def aggregate_closed_candles(
    candles: Iterable[Candle],
    target: Timeframe,
    *,
    as_of: datetime,
    sessions: Iterable[MarketSession] | None = None,
) -> tuple[Candle, ...]:
    """Aggregate only complete buckets whose full inputs were known at ``as_of``.

    Input candles must have a uniform timeframe. Intraday buckets align to 09:15 IST,
    not midnight. Daily bars require every expected regular-session source candle.
    Weekly bars require five complete daily candles and become available after Friday.
    """
    cutoff = _utc(as_of)
    source = sorted(candles, key=lambda candle: candle.timestamp)
    if not source:
        return ()
    base = source[0].timeframe_seconds
    if any(candle.instrument_id != source[0].instrument_id for candle in source):
        raise ValueError("source candles must belong to one instrument")
    if any(candle.timeframe_seconds != base for candle in source):
        raise ValueError("source candles must use one timeframe")
    if int(target) <= base or int(target) % base != 0:
        raise ValueError("target must be a larger whole multiple of the source timeframe")
    available = [
        candle
        for candle in source
        if candle.is_closed and _source_available_at(candle, base) <= cutoff
    ]
    if target is Timeframe.WEEK_1:
        return _aggregate_weekly(available, cutoff, sessions)
    grouped: dict[datetime, list[Candle]] = defaultdict(list)
    for candle in available:
        local = candle.timestamp.astimezone(INDIA)
        session_open = datetime.combine(local.date(), NSE_OPEN, INDIA)
        session_close = datetime.combine(local.date(), NSE_CLOSE, INDIA)
        if not session_open <= local < session_close:
            continue
        if target is Timeframe.DAY_1:
            bucket = session_open
        else:
            elapsed = int((local - session_open).total_seconds())
            bucket = session_open + timedelta(seconds=(elapsed // int(target)) * int(target))
        grouped[bucket.astimezone(UTC)].append(candle)

    output: list[Candle] = []
    for bucket, members in sorted(grouped.items()):
        local_day = bucket.astimezone(INDIA).date()
        session_close = datetime.combine(local_day, NSE_CLOSE, INDIA).astimezone(UTC)
        bucket_end = (
            session_close
            if target is Timeframe.DAY_1
            else min(bucket + timedelta(seconds=int(target)), session_close)
        )
        duration = int((bucket_end - bucket).total_seconds())
        expected = duration // base
        if bucket_end <= cutoff and len(members) == expected and _is_contiguous(members, base):
            output.append(_combine(members, bucket, int(target)))
    return tuple(output)


def _aggregate_weekly(
    candles: list[Candle], cutoff: datetime, sessions: Iterable[MarketSession] | None
) -> tuple[Candle, ...]:
    if not candles or candles[0].timeframe_seconds != Timeframe.DAY_1:
        raise ValueError("weekly aggregation requires daily source candles")
    groups: dict[date, list[Candle]] = defaultdict(list)
    for candle in candles:
        local_date = candle.timestamp.astimezone(INDIA).date()
        groups[local_date - timedelta(days=local_date.weekday())].append(candle)
    calendar: dict[date, MarketSession] | None = None
    if sessions is not None:
        calendar = {}
        for session in sessions:
            if session.exchange is not Exchange.NSE:
                raise ValueError("weekly NSE candles require NSE calendar sessions")
            if session.session_date in calendar:
                raise ValueError("duplicate calendar session date")
            if session.opens_at.astimezone(INDIA).date() != session.session_date:
                raise ValueError("calendar session open date does not match session date")
            calendar[session.session_date] = session
    output = []
    for monday, members in sorted(groups.items()):
        if calendar is None:
            closes_at = datetime.combine(monday + timedelta(days=4), NSE_CLOSE, INDIA).astimezone(
                UTC
            )
            complete = len(members) == 5
        else:
            weekdays = {monday + timedelta(days=day) for day in range(5)}
            if not weekdays.issubset(calendar):
                raise ValueError("weekly calendar does not cover all five weekdays")
            trading = {
                day: session
                for day, session in calendar.items()
                if monday <= day < monday + timedelta(days=7) and session.is_trading_day
            }
            dates = {member.timestamp.astimezone(INDIA).date() for member in members}
            complete = (
                len(members) == len(dates)
                and dates == set(trading)
                and all(
                    member.timestamp == trading[member.timestamp.astimezone(INDIA).date()].opens_at
                    for member in members
                    if member.timestamp.astimezone(INDIA).date() in trading
                )
            )
            closes_at = max((item.closes_at for item in trading.values()), default=cutoff)
        if complete and members and closes_at <= cutoff:
            output.append(_combine(members, members[0].timestamp, int(Timeframe.WEEK_1)))
    return tuple(output)


def _is_contiguous(candles: list[Candle], seconds: int) -> bool:
    ordered = sorted(candles, key=lambda candle: candle.timestamp)
    return all(
        right.timestamp - left.timestamp == timedelta(seconds=seconds)
        for left, right in pairwise(ordered)
    )


def _combine(candles: list[Candle], timestamp: datetime, timeframe: int) -> Candle:
    ordered = sorted(candles, key=lambda candle: candle.timestamp)
    open_interest = ordered[-1].open_interest
    return Candle(
        instrument_id=ordered[0].instrument_id,
        timestamp=timestamp,
        timeframe_seconds=timeframe,
        open=ordered[0].open,
        high=max(candle.high for candle in ordered),
        low=min(candle.low for candle in ordered),
        close=ordered[-1].close,
        volume=sum((candle.volume for candle in ordered), start=Decimal(0)),
        open_interest=open_interest,
        is_closed=True,
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    return value.astimezone(UTC)


def _source_available_at(candle: Candle, timeframe: int) -> datetime:
    if timeframe == Timeframe.DAY_1:
        local_date = candle.timestamp.astimezone(INDIA).date()
        return datetime.combine(local_date, NSE_CLOSE, INDIA).astimezone(UTC)
    return candle.timestamp + timedelta(seconds=timeframe)


def candle_available_at(candle: Candle) -> datetime:
    """Availability of an already closed source candle, including NSE daily closes."""
    return _source_available_at(candle, candle.timeframe_seconds)
