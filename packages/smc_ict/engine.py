"""Causal and non-repainting market-structure primitives.

This module deliberately implements only concepts with explicit mathematical
rules. It does not infer institutional intent from price patterns.
"""

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum
from itertools import pairwise
from zoneinfo import ZoneInfo

from packages.domain.models import Candle

INDIA = ZoneInfo("Asia/Kolkata")


class Direction(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"


class StructureKind(StrEnum):
    BREAK_OF_STRUCTURE = "break_of_structure"
    CHANGE_OF_CHARACTER = "change_of_character"
    MARKET_STRUCTURE_SHIFT = "market_structure_shift"


class StructureScope(StrEnum):
    INTERNAL = "internal"
    EXTERNAL = "external"


class LiquiditySide(StrEnum):
    BUY_SIDE = "buy_side"
    SELL_SIDE = "sell_side"


class GapStatus(StrEnum):
    ACTIVE = "active"
    MITIGATED = "mitigated"
    INVALIDATED = "invalidated"


class BlockKind(StrEnum):
    ORDER_BLOCK = "order_block"
    MITIGATION_BLOCK = "mitigation_block"
    BREAKER_BLOCK = "breaker_block"


class BlockStatus(StrEnum):
    ACTIVE = "active"
    MITIGATED = "mitigated"
    INVALIDATED = "invalidated"


class ReferenceKind(StrEnum):
    PREVIOUS_DAY_HIGH = "previous_day_high"
    PREVIOUS_DAY_LOW = "previous_day_low"
    PREVIOUS_WEEK_HIGH = "previous_week_high"
    PREVIOUS_WEEK_LOW = "previous_week_low"
    SESSION_HIGH = "session_high"
    SESSION_LOW = "session_low"


class ZoneKind(StrEnum):
    PREMIUM = "premium"
    DISCOUNT = "discount"
    BULLISH_OTE = "bullish_ote"
    BEARISH_OTE = "bearish_ote"


@dataclass(frozen=True, slots=True)
class SMCConfig:
    """Versioned thresholds for deterministic detection."""

    swing_left: int = 2
    swing_right: int = 2
    internal_swing_left: int = 1
    internal_swing_right: int = 1
    minimum_gap_percent: Decimal = Decimal("0.05")
    sweep_tolerance_percent: Decimal = Decimal("0")
    equal_level_tolerance_percent: Decimal = Decimal("0.05")
    displacement_lookback: int = 10
    displacement_body_multiple: Decimal = Decimal("1.5")
    displacement_close_location: Decimal = Decimal("0.75")
    order_block_lookback: int = 5
    rule_version: str = "smc-rules-v1"

    def __post_init__(self) -> None:
        if (
            self.swing_left < 1
            or self.swing_right < 1
            or self.internal_swing_left < 1
            or self.internal_swing_right < 1
        ):
            raise ValueError("swing windows must be positive")
        if (
            self.minimum_gap_percent < 0
            or self.sweep_tolerance_percent < 0
            or self.equal_level_tolerance_percent < 0
        ):
            raise ValueError("percentage thresholds cannot be negative")
        if self.displacement_lookback < 1 or self.displacement_body_multiple <= 0:
            raise ValueError("displacement lookback and body multiple must be positive")
        if self.order_block_lookback < 1:
            raise ValueError("order block lookback must be positive")
        if not Decimal("0.5") <= self.displacement_close_location <= 1:
            raise ValueError("displacement close location must be between 0.5 and 1")
        if not self.rule_version.strip():
            raise ValueError("rule_version cannot be empty")


@dataclass(frozen=True, slots=True)
class SwingPoint:
    scope: StructureScope
    direction: Direction
    price: Decimal
    candle_timestamp: datetime
    confirmed_at: datetime
    evidence: tuple[datetime, ...]
    confidence: Decimal
    invalidation: str


@dataclass(frozen=True, slots=True)
class MarketStructureEvent:
    scope: StructureScope
    kind: StructureKind
    direction: Direction
    level: Decimal
    detected_at: datetime
    swing_timestamp: datetime
    evidence: tuple[datetime, ...]
    confidence: Decimal
    invalidation: str
    explanation: str


@dataclass(frozen=True, slots=True)
class Displacement:
    direction: Direction
    detected_at: datetime
    low: Decimal
    high: Decimal
    body: Decimal
    average_prior_body: Decimal
    close_location: Decimal
    evidence: tuple[datetime, ...]
    confidence: Decimal
    invalidation: str
    explanation: str


@dataclass(frozen=True, slots=True)
class EqualLevel:
    side: LiquiditySide
    lower: Decimal
    upper: Decimal
    detected_at: datetime
    swing_timestamps: tuple[datetime, datetime]
    evidence: tuple[datetime, ...]
    confidence: Decimal
    invalidation: str
    explanation: str


@dataclass(frozen=True, slots=True)
class ReferenceLevel:
    kind: ReferenceKind
    price: Decimal
    available_at: datetime
    evidence: tuple[datetime, ...]
    explanation: str


@dataclass(frozen=True, slots=True)
class PriceZone:
    kind: ZoneKind
    lower: Decimal
    upper: Decimal
    available_at: datetime
    evidence: tuple[datetime, ...]
    invalidation: str
    explanation: str


@dataclass(frozen=True, slots=True)
class KillZone:
    name: str
    start: time
    end: time
    timezone_name: str


@dataclass(frozen=True, slots=True)
class PriceBlock:
    kind: BlockKind
    direction: Direction
    lower: Decimal
    upper: Decimal
    origin_timestamp: datetime
    detected_at: datetime
    status: BlockStatus
    mitigated_at: datetime | None
    invalidated_at: datetime | None
    evidence: tuple[datetime, ...]
    confidence: Decimal
    invalidation: str
    explanation: str


DEFAULT_KILL_ZONES = (
    KillZone("asia", time(5, 30), time(9, 30), "Asia/Kolkata"),
    KillZone("nse_open", time(9, 15), time(10, 15), "Asia/Kolkata"),
    KillZone("london_fixed_ist", time(12, 30), time(15, 30), "Asia/Kolkata"),
    KillZone("new_york_fixed_ist", time(18, 30), time(21, 30), "Asia/Kolkata"),
)


@dataclass(frozen=True, slots=True)
class FairValueGap:
    direction: Direction
    lower: Decimal
    upper: Decimal
    detected_at: datetime
    consequent_encroachment: Decimal
    status: GapStatus
    mitigated_at: datetime | None
    invalidated_at: datetime | None
    evidence: tuple[datetime, ...]
    confidence: Decimal
    invalidation: str
    explanation: str


@dataclass(frozen=True, slots=True)
class InverseFairValueGap:
    """An FVG closed through in the opposite direction after formation."""

    direction: Direction
    lower: Decimal
    upper: Decimal
    source_detected_at: datetime
    detected_at: datetime
    consequent_encroachment: Decimal
    evidence: tuple[datetime, ...]
    confidence: Decimal
    invalidation: str
    explanation: str


@dataclass(frozen=True, slots=True)
class LiquiditySweep:
    direction: Direction
    level: Decimal
    extreme: Decimal
    detected_at: datetime
    swing_timestamp: datetime
    evidence: tuple[datetime, ...]
    confidence: Decimal
    invalidation: str
    explanation: str


@dataclass(frozen=True, slots=True)
class Overlay:
    """Broker/frontend-neutral chart primitive."""

    kind: str
    start: datetime
    end: datetime
    lower: Decimal
    upper: Decimal
    label: str
    color: str


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    rule_version: str
    as_of: datetime | None
    swings: tuple[SwingPoint, ...]
    internal_swings: tuple[SwingPoint, ...]
    internal_structure: tuple[MarketStructureEvent, ...]
    displacements: tuple[Displacement, ...]
    equal_levels: tuple[EqualLevel, ...]
    reference_levels: tuple[ReferenceLevel, ...]
    price_zones: tuple[PriceZone, ...]
    active_kill_zones: tuple[str, ...]
    price_blocks: tuple[PriceBlock, ...]
    structure: tuple[MarketStructureEvent, ...]
    fair_value_gaps: tuple[FairValueGap, ...]
    inverse_fair_value_gaps: tuple[InverseFairValueGap, ...]
    liquidity_sweeps: tuple[LiquiditySweep, ...]
    overlays: tuple[Overlay, ...]


def _confidence(distance: Decimal, reference: Decimal) -> Decimal:
    """Scale objective pattern magnitude into [0.5, 1.0]."""
    if reference <= 0:
        return Decimal("0.5")
    return min(Decimal("1"), Decimal("0.5") + distance / reference)


def _closed_at(candle: Candle) -> datetime:
    """Return the first instant at which an interval-start candle is knowable."""
    return candle.timestamp + timedelta(seconds=candle.timeframe_seconds)


def _validate(candles: tuple[Candle, ...]) -> None:
    if not candles:
        return
    instrument = candles[0].instrument_id
    timeframe = candles[0].timeframe_seconds
    previous: datetime | None = None
    for candle in candles:
        if not candle.is_closed:
            raise ValueError("SMC analysis accepts closed candles only")
        if candle.instrument_id != instrument or candle.timeframe_seconds != timeframe:
            raise ValueError("candles must belong to one instrument and timeframe")
        if previous is not None and candle.timestamp <= previous:
            raise ValueError("candles must have unique, strictly increasing timestamps")
        previous = candle.timestamp


def _swings(
    candles: tuple[Candle, ...], *, left: int, right: int, scope: StructureScope
) -> tuple[SwingPoint, ...]:
    result: list[SwingPoint] = []
    width = left + right
    for confirmation_index in range(width, len(candles)):
        pivot_index = confirmation_index - right
        window = candles[pivot_index - left : confirmation_index + 1]
        pivot = candles[pivot_index]
        evidence = tuple(item.timestamp for item in window)
        other_highs = [item.high for offset, item in enumerate(window) if offset != left]
        other_lows = [item.low for offset, item in enumerate(window) if offset != left]
        if all(pivot.high > value for value in other_highs):
            result.append(
                SwingPoint(
                    scope,
                    Direction.BEARISH,
                    pivot.high,
                    pivot.timestamp,
                    _closed_at(candles[confirmation_index]),
                    evidence,
                    _confidence(pivot.high - max(other_highs), pivot.high),
                    f"invalid if a closed candle closes above {pivot.high}",
                )
            )
        if all(pivot.low < value for value in other_lows):
            result.append(
                SwingPoint(
                    scope,
                    Direction.BULLISH,
                    pivot.low,
                    pivot.timestamp,
                    _closed_at(candles[confirmation_index]),
                    evidence,
                    _confidence(min(other_lows) - pivot.low, pivot.low),
                    f"invalid if a closed candle closes below {pivot.low}",
                )
            )
    return tuple(result)


def _displacements(candles: tuple[Candle, ...], config: SMCConfig) -> tuple[Displacement, ...]:
    """Detect large real bodies whose close is near the directional extreme."""
    result: list[Displacement] = []
    for index in range(config.displacement_lookback, len(candles)):
        candle = candles[index]
        prior = candles[index - config.displacement_lookback : index]
        average = sum((abs(item.close - item.open) for item in prior), Decimal(0)) / len(prior)
        body = abs(candle.close - candle.open)
        candle_range = candle.high - candle.low
        if average == 0 or candle_range == 0 or body < average * config.displacement_body_multiple:
            continue
        location = (candle.close - candle.low) / candle_range
        bullish = candle.close > candle.open and location >= config.displacement_close_location
        bearish = (
            candle.close < candle.open
            and location <= Decimal(1) - config.displacement_close_location
        )
        if not bullish and not bearish:
            continue
        direction = Direction.BULLISH if bullish else Direction.BEARISH
        result.append(
            Displacement(
                direction,
                _closed_at(candle),
                candle.low,
                candle.high,
                body,
                average,
                location,
                tuple(item.timestamp for item in (*prior, candle)),
                min(Decimal(1), Decimal("0.5") + body / average / 10),
                f"invalid if a later close crosses {candle.low if bullish else candle.high}",
                f"body {body} is {body / average:.2f}x the prior-body mean and closes at "
                f"{location:.2%} of its range",
            )
        )
    return tuple(result)


def _equal_levels(swings: tuple[SwingPoint, ...], config: SMCConfig) -> tuple[EqualLevel, ...]:
    """Pair consecutive same-side confirmed swings inside a percentage tolerance."""
    result: list[EqualLevel] = []
    for direction in Direction:
        matching = [item for item in swings if item.direction is direction]
        for first, second in pairwise(matching):
            midpoint = (first.price + second.price) / 2
            tolerance = midpoint * config.equal_level_tolerance_percent / 100
            difference = abs(first.price - second.price)
            if difference > tolerance:
                continue
            side = (
                LiquiditySide.BUY_SIDE
                if direction is Direction.BEARISH
                else LiquiditySide.SELL_SIDE
            )
            result.append(
                EqualLevel(
                    side,
                    min(first.price, second.price),
                    max(first.price, second.price),
                    max(first.confirmed_at, second.confirmed_at),
                    (first.candle_timestamp, second.candle_timestamp),
                    (*first.evidence, *second.evidence),
                    Decimal(1) if tolerance == 0 else Decimal(1) - difference / (2 * tolerance),
                    f"invalid when a closed candle closes beyond the {side.value} band",
                    f"two confirmed swings differ by {difference}, within tolerance {tolerance}",
                )
            )
    return tuple(result)


def _level(
    kind: ReferenceKind, candles: list[Candle], *, high: bool, available_at: datetime
) -> ReferenceLevel:
    price = max(item.high for item in candles) if high else min(item.low for item in candles)
    return ReferenceLevel(
        kind,
        price,
        available_at,
        tuple(item.timestamp for item in candles),
        f"{kind.value.replace('_', ' ')} from {len(candles)} closed candles",
    )


def _reference_levels(candles: tuple[Candle, ...]) -> tuple[ReferenceLevel, ...]:
    if not candles:
        return ()
    as_of = _closed_at(candles[-1])
    local_dates = [item.timestamp.astimezone(INDIA).date() for item in candles]
    current_date = local_dates[-1]
    current_week = current_date.isocalendar()[:2]
    by_date: dict[date, list[Candle]] = {}
    by_week: dict[tuple[int, int], list[Candle]] = {}
    for candle, local_date in zip(candles, local_dates, strict=True):
        by_date.setdefault(local_date, []).append(candle)
        by_week.setdefault(local_date.isocalendar()[:2], []).append(candle)
    result: list[ReferenceLevel] = []
    prior_dates = sorted(key for key in by_date if key < current_date)
    if prior_dates:
        previous = by_date[prior_dates[-1]]
        available = _closed_at(previous[-1])
        result.extend(
            (
                _level(
                    ReferenceKind.PREVIOUS_DAY_HIGH, previous, high=True, available_at=available
                ),
                _level(
                    ReferenceKind.PREVIOUS_DAY_LOW, previous, high=False, available_at=available
                ),
            )
        )
    prior_weeks = sorted(key for key in by_week if key < current_week)
    if prior_weeks:
        previous = by_week[prior_weeks[-1]]
        available = _closed_at(previous[-1])
        result.extend(
            (
                _level(
                    ReferenceKind.PREVIOUS_WEEK_HIGH, previous, high=True, available_at=available
                ),
                _level(
                    ReferenceKind.PREVIOUS_WEEK_LOW, previous, high=False, available_at=available
                ),
            )
        )
    session = by_date[current_date]
    result.extend(
        (
            _level(ReferenceKind.SESSION_HIGH, session, high=True, available_at=as_of),
            _level(ReferenceKind.SESSION_LOW, session, high=False, available_at=as_of),
        )
    )
    return tuple(result)


def _price_zones(swings: tuple[SwingPoint, ...]) -> tuple[PriceZone, ...]:
    highs = [item for item in swings if item.direction is Direction.BEARISH]
    lows = [item for item in swings if item.direction is Direction.BULLISH]
    if not highs or not lows:
        return ()
    high, low = highs[-1], lows[-1]
    if high.price <= low.price:
        return ()
    width = high.price - low.price
    midpoint = low.price + width / 2
    available = max(high.confirmed_at, low.confirmed_at)
    evidence = (low.candle_timestamp, high.candle_timestamp)
    return (
        PriceZone(
            ZoneKind.DISCOUNT,
            low.price,
            midpoint,
            available,
            evidence,
            f"invalid when dealing range {low.price}-{high.price} is replaced",
            "lower half of the latest confirmed dealing range",
        ),
        PriceZone(
            ZoneKind.PREMIUM,
            midpoint,
            high.price,
            available,
            evidence,
            f"invalid when dealing range {low.price}-{high.price} is replaced",
            "upper half of the latest confirmed dealing range",
        ),
        PriceZone(
            ZoneKind.BULLISH_OTE,
            low.price + width * Decimal("0.62"),
            low.price + width * Decimal("0.79"),
            available,
            evidence,
            f"invalid below dealing-range low {low.price}",
            "62%-79% retracement measured upward from the confirmed low",
        ),
        PriceZone(
            ZoneKind.BEARISH_OTE,
            high.price - width * Decimal("0.79"),
            high.price - width * Decimal("0.62"),
            available,
            evidence,
            f"invalid above dealing-range high {high.price}",
            "62%-79% retracement measured downward from the confirmed high",
        ),
    )


def active_kill_zones(
    timestamp: datetime, zones: tuple[KillZone, ...] = DEFAULT_KILL_ZONES
) -> tuple[str, ...]:
    """Return configured half-open local-time windows active at an aware timestamp."""
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("kill-zone timestamp must be timezone-aware")
    result: list[str] = []
    for zone in zones:
        local_time = timestamp.astimezone(ZoneInfo(zone.timezone_name)).time().replace(tzinfo=None)
        active = (
            zone.start <= local_time < zone.end
            if zone.start <= zone.end
            else local_time >= zone.start or local_time < zone.end
        )
        if active:
            result.append(zone.name)
    return tuple(result)


def _fair_value_gaps(candles: tuple[Candle, ...], config: SMCConfig) -> tuple[FairValueGap, ...]:
    result: list[FairValueGap] = []
    for index in range(2, len(candles)):
        first, current = candles[index - 2], candles[index]
        candidates = (
            (Direction.BULLISH, first.high, current.low),
            (Direction.BEARISH, current.high, first.low),
        )
        for direction, lower, upper in candidates:
            if upper <= lower:
                continue
            midpoint = (lower + upper) / 2
            gap_percent = (upper - lower) / midpoint * 100
            if gap_percent < config.minimum_gap_percent:
                continue
            invalidation = (
                f"invalid when a closed candle trades at or below {lower}"
                if direction is Direction.BULLISH
                else f"invalid when a closed candle trades at or above {upper}"
            )
            result.append(
                FairValueGap(
                    direction,
                    lower,
                    upper,
                    _closed_at(current),
                    midpoint,
                    GapStatus.ACTIVE,
                    None,
                    None,
                    tuple(item.timestamp for item in candles[index - 2 : index + 1]),
                    _confidence(upper - lower, midpoint),
                    invalidation,
                    f"{direction.value} three-candle imbalance from {lower} to {upper}",
                )
            )
    return tuple(result)


def _gap_lifecycle(
    candles: tuple[Candle, ...], gaps: tuple[FairValueGap, ...]
) -> tuple[tuple[FairValueGap, ...], tuple[InverseFairValueGap, ...]]:
    """Evaluate each gap only against candles closed after its detection."""
    updated: list[FairValueGap] = []
    inverse: list[InverseFairValueGap] = []
    for gap in gaps:
        mitigated_at: datetime | None = None
        invalidated_at: datetime | None = None
        for candle in candles:
            candle_closed_at = _closed_at(candle)
            if candle_closed_at <= gap.detected_at:
                continue
            if gap.direction is Direction.BULLISH:
                touched = candle.low < gap.upper
                invalidated = candle.low <= gap.lower
                inverted = candle.close < gap.lower
                inverse_direction = Direction.BEARISH
                inverse_invalidation = f"invalid if a closed candle closes above {gap.upper}"
            else:
                touched = candle.high > gap.lower
                invalidated = candle.high >= gap.upper
                inverted = candle.close > gap.upper
                inverse_direction = Direction.BULLISH
                inverse_invalidation = f"invalid if a closed candle closes below {gap.lower}"
            if touched and mitigated_at is None:
                mitigated_at = candle_closed_at
            if invalidated:
                invalidated_at = candle_closed_at
            if inverted:
                inverse.append(
                    InverseFairValueGap(
                        inverse_direction,
                        gap.lower,
                        gap.upper,
                        gap.detected_at,
                        candle_closed_at,
                        gap.consequent_encroachment,
                        (*gap.evidence, candle.timestamp),
                        gap.confidence,
                        inverse_invalidation,
                        f"{gap.direction.value} FVG closed through {gap.lower}-{gap.upper}",
                    )
                )
                break
            if invalidated:
                break
        status = (
            GapStatus.INVALIDATED
            if invalidated_at is not None
            else GapStatus.MITIGATED
            if mitigated_at is not None
            else GapStatus.ACTIVE
        )
        updated.append(
            replace(
                gap,
                status=status,
                mitigated_at=mitigated_at,
                invalidated_at=invalidated_at,
            )
        )
    return tuple(updated), tuple(inverse)


def _structure_and_sweeps(
    candles: tuple[Candle, ...],
    swings: tuple[SwingPoint, ...],
    displacements: tuple[Displacement, ...],
    config: SMCConfig,
    scope: StructureScope,
) -> tuple[tuple[MarketStructureEvent, ...], tuple[LiquiditySweep, ...]]:
    structure: list[MarketStructureEvent] = []
    sweeps: list[LiquiditySweep] = []
    trend: Direction | None = None
    displacement_by_key = {(item.direction, item.detected_at): item for item in displacements}
    consumed: set[tuple[Direction, datetime]] = set()
    for candle in candles:
        candle_closed_at = _closed_at(candle)
        # A swing confirmed by the current candle cannot also be broken by that
        # candle: its right-hand evidence was not closed before this event.
        available = [swing for swing in swings if swing.confirmed_at < candle_closed_at]
        for direction in Direction:
            matching = [swing for swing in available if swing.direction is direction]
            if not matching:
                continue
            swing = matching[-1]
            key = (direction, swing.candle_timestamp)
            tolerance = swing.price * config.sweep_tolerance_percent / 100
            if direction is Direction.BEARISH:
                swept = candle.high > swing.price + tolerance and candle.close <= swing.price
                broken = candle.close > swing.price
                break_direction = Direction.BULLISH
                sweep_direction = Direction.BEARISH
                extreme = candle.high
            else:
                swept = candle.low < swing.price - tolerance and candle.close >= swing.price
                broken = candle.close < swing.price
                break_direction = Direction.BEARISH
                sweep_direction = Direction.BULLISH
                extreme = candle.low
            if swept:
                distance = abs(extreme - swing.price)
                sweeps.append(
                    LiquiditySweep(
                        sweep_direction,
                        swing.price,
                        extreme,
                        candle_closed_at,
                        swing.candle_timestamp,
                        (swing.candle_timestamp, swing.confirmed_at, candle.timestamp),
                        _confidence(distance, swing.price),
                        f"invalid if price closes beyond swept level {swing.price}",
                        f"price traded beyond {swing.price} but closed back inside the prior range",
                    )
                )
            if broken and key not in consumed:
                kind = (
                    StructureKind.CHANGE_OF_CHARACTER
                    if trend is not None and trend is not break_direction
                    else StructureKind.BREAK_OF_STRUCTURE
                )
                distance = abs(candle.close - swing.price)
                structure.append(
                    MarketStructureEvent(
                        scope,
                        kind,
                        break_direction,
                        swing.price,
                        candle_closed_at,
                        swing.candle_timestamp,
                        (swing.candle_timestamp, swing.confirmed_at, candle.timestamp),
                        _confidence(distance, swing.price),
                        f"invalid if a closed candle reverses through {swing.price}",
                        f"{candle.close} closed beyond confirmed swing level {swing.price}",
                    )
                )
                displacement = displacement_by_key.get((break_direction, candle_closed_at))
                if kind is StructureKind.CHANGE_OF_CHARACTER and displacement is not None:
                    evidence = tuple(
                        sorted(
                            {
                                swing.candle_timestamp,
                                swing.confirmed_at,
                                *displacement.evidence,
                            }
                        )
                    )
                    structure.append(
                        MarketStructureEvent(
                            scope,
                            StructureKind.MARKET_STRUCTURE_SHIFT,
                            break_direction,
                            swing.price,
                            candle_closed_at,
                            swing.candle_timestamp,
                            evidence,
                            min(_confidence(distance, swing.price), displacement.confidence),
                            f"invalid if a closed candle reverses through {swing.price}",
                            "CHOCH and qualifying displacement occurred on the same closed candle",
                        )
                    )
                consumed.add(key)
                trend = break_direction
    return tuple(structure), tuple(sweeps)


def _price_blocks(
    candles: tuple[Candle, ...],
    structure: tuple[MarketStructureEvent, ...],
    displacements: tuple[Displacement, ...],
    config: SMCConfig,
) -> tuple[PriceBlock, ...]:
    """Build order-block lifecycle from displacement-confirmed structure breaks."""
    displacement_by_key = {(item.direction, item.detected_at): item for item in displacements}
    candle_index = {_closed_at(item): index for index, item in enumerate(candles)}
    source_blocks: list[PriceBlock] = []
    seen: set[tuple[Direction, datetime]] = set()
    for event in structure:
        key = (event.direction, event.detected_at)
        displacement = displacement_by_key.get(key)
        if displacement is None or key in seen:
            continue
        break_index = candle_index[event.detected_at]
        start = max(0, break_index - config.order_block_lookback)
        candidates = candles[start:break_index]
        origin = next(
            (
                candle
                for candle in reversed(candidates)
                if (event.direction is Direction.BULLISH and candle.close < candle.open)
                or (event.direction is Direction.BEARISH and candle.close > candle.open)
            ),
            None,
        )
        if origin is None:
            continue
        source_blocks.append(
            PriceBlock(
                BlockKind.ORDER_BLOCK,
                event.direction,
                origin.low,
                origin.high,
                origin.timestamp,
                event.detected_at,
                BlockStatus.ACTIVE,
                None,
                None,
                tuple(sorted({origin.timestamp, *event.evidence, *displacement.evidence})),
                min(event.confidence, displacement.confidence),
                (
                    f"invalid on a close below {origin.low}"
                    if event.direction is Direction.BULLISH
                    else f"invalid on a close above {origin.high}"
                ),
                f"last opposing candle before {event.direction.value} displacement-confirmed break",
            )
        )
        seen.add(key)

    result: list[PriceBlock] = []
    for block in source_blocks:
        mitigated_at: datetime | None = None
        invalidated_at: datetime | None = None
        for candle in candles:
            closed_at = _closed_at(candle)
            if closed_at <= block.detected_at:
                continue
            overlaps = candle.low <= block.upper and candle.high >= block.lower
            invalidated = (
                candle.close < block.lower
                if block.direction is Direction.BULLISH
                else candle.close > block.upper
            )
            if overlaps and mitigated_at is None:
                mitigated_at = closed_at
                result.append(
                    PriceBlock(
                        BlockKind.MITIGATION_BLOCK,
                        block.direction,
                        block.lower,
                        block.upper,
                        block.origin_timestamp,
                        closed_at,
                        BlockStatus.MITIGATED,
                        closed_at,
                        None,
                        (*block.evidence, candle.timestamp),
                        block.confidence,
                        block.invalidation,
                        "first closed-candle retest of the source order-block range",
                    )
                )
            if invalidated:
                invalidated_at = closed_at
                opposite = (
                    Direction.BEARISH if block.direction is Direction.BULLISH else Direction.BULLISH
                )
                result.append(
                    PriceBlock(
                        BlockKind.BREAKER_BLOCK,
                        opposite,
                        block.lower,
                        block.upper,
                        block.origin_timestamp,
                        closed_at,
                        BlockStatus.ACTIVE,
                        None,
                        None,
                        (*block.evidence, candle.timestamp),
                        block.confidence,
                        (
                            f"invalid on a close above {block.upper}"
                            if opposite is Direction.BEARISH
                            else f"invalid on a close below {block.lower}"
                        ),
                        f"{block.direction.value} order block failed by directional close-through",
                    )
                )
                break
        status = (
            BlockStatus.INVALIDATED
            if invalidated_at is not None
            else BlockStatus.MITIGATED
            if mitigated_at is not None
            else BlockStatus.ACTIVE
        )
        result.append(
            replace(
                block,
                status=status,
                mitigated_at=mitigated_at,
                invalidated_at=invalidated_at,
            )
        )
    return tuple(sorted(result, key=lambda item: (item.detected_at, item.kind.value)))


def _overlays(
    swings: tuple[SwingPoint, ...],
    internal_swings: tuple[SwingPoint, ...],
    displacements: tuple[Displacement, ...],
    equal_levels: tuple[EqualLevel, ...],
    reference_levels: tuple[ReferenceLevel, ...],
    price_zones: tuple[PriceZone, ...],
    price_blocks: tuple[PriceBlock, ...],
    structure: tuple[MarketStructureEvent, ...],
    internal_structure: tuple[MarketStructureEvent, ...],
    gaps: tuple[FairValueGap, ...],
    inverse_gaps: tuple[InverseFairValueGap, ...],
    sweeps: tuple[LiquiditySweep, ...],
    as_of: datetime | None,
) -> tuple[Overlay, ...]:
    result = [
        Overlay(
            "swing",
            item.candle_timestamp,
            item.confirmed_at,
            item.price,
            item.price,
            f"confirmed {item.scope.value} {item.direction.value} swing",
            "#22c55e" if item.direction is Direction.BULLISH else "#ef4444",
        )
        for item in (*swings, *internal_swings)
    ]
    result.extend(
        Overlay(
            item.kind.value,
            item.origin_timestamp,
            item.invalidated_at or as_of or item.detected_at,
            item.lower,
            item.upper,
            f"{item.direction.value} {item.kind.value.replace('_', ' ')}",
            ("#22c55e" if item.direction is Direction.BULLISH else "#ef4444"),
        )
        for item in price_blocks
    )
    result.extend(
        Overlay(
            item.kind.value,
            item.available_at,
            as_of or item.available_at,
            item.price,
            item.price,
            item.kind.value.replace("_", " "),
            "#64748b",
        )
        for item in reference_levels
    )
    result.extend(
        Overlay(
            item.kind.value,
            item.available_at,
            as_of or item.available_at,
            item.lower,
            item.upper,
            item.kind.value.replace("_", " "),
            "#0ea5e9" if item.kind is ZoneKind.DISCOUNT else "#f59e0b",
        )
        for item in price_zones
    )
    result.extend(
        Overlay(
            "displacement",
            item.detected_at,
            item.detected_at,
            item.low,
            item.high,
            f"{item.direction.value} displacement",
            "#14b8a6" if item.direction is Direction.BULLISH else "#fb7185",
        )
        for item in displacements
    )
    result.extend(
        Overlay(
            "equal_levels",
            item.swing_timestamps[0],
            as_of or item.detected_at,
            item.lower,
            item.upper,
            item.side.value.replace("_", " "),
            "#eab308",
        )
        for item in equal_levels
    )
    result.extend(
        Overlay(
            item.kind.value,
            item.swing_timestamp,
            item.detected_at,
            item.level,
            item.level,
            f"{item.scope.value} {item.kind.value.replace('_', ' ')}",
            "#3b82f6" if item.direction is Direction.BULLISH else "#f97316",
        )
        for item in (*structure, *internal_structure)
    )
    result.extend(
        Overlay(
            "fair_value_gap",
            item.evidence[0],
            item.invalidated_at or as_of or item.detected_at,
            item.lower,
            item.upper,
            f"{item.direction.value} FVG ({item.status.value})",
            "#10b981" if item.direction is Direction.BULLISH else "#f43f5e",
        )
        for item in gaps
    )
    result.extend(
        Overlay(
            "inverse_fair_value_gap",
            item.detected_at,
            as_of or item.detected_at,
            item.lower,
            item.upper,
            f"{item.direction.value} IFVG",
            "#06b6d4" if item.direction is Direction.BULLISH else "#e11d48",
        )
        for item in inverse_gaps
    )
    result.extend(
        Overlay(
            "liquidity_sweep",
            item.swing_timestamp,
            item.detected_at,
            min(item.level, item.extreme),
            max(item.level, item.extreme),
            f"{item.direction.value} liquidity sweep",
            "#a855f7",
        )
        for item in sweeps
    )
    return tuple(result)


def analyze(candles: tuple[Candle, ...], config: SMCConfig | None = None) -> AnalysisResult:
    """Analyze a closed, chronological candle snapshot as known at its final timestamp."""
    rules = config or SMCConfig()
    _validate(candles)
    swings = _swings(
        candles,
        left=rules.swing_left,
        right=rules.swing_right,
        scope=StructureScope.EXTERNAL,
    )
    internal_swings = _swings(
        candles,
        left=rules.internal_swing_left,
        right=rules.internal_swing_right,
        scope=StructureScope.INTERNAL,
    )
    displacements = _displacements(candles, rules)
    equal_levels = _equal_levels(swings, rules)
    reference_levels = _reference_levels(candles)
    price_zones = _price_zones(swings)
    gaps, inverse_gaps = _gap_lifecycle(candles, _fair_value_gaps(candles, rules))
    structure, sweeps = _structure_and_sweeps(
        candles, swings, displacements, rules, StructureScope.EXTERNAL
    )
    internal_structure, _ = _structure_and_sweeps(
        candles, internal_swings, displacements, rules, StructureScope.INTERNAL
    )
    price_blocks = _price_blocks(candles, structure, displacements, rules)
    return AnalysisResult(
        rules.rule_version,
        _closed_at(candles[-1]) if candles else None,
        swings,
        internal_swings,
        internal_structure,
        displacements,
        equal_levels,
        reference_levels,
        price_zones,
        active_kill_zones(_closed_at(candles[-1])) if candles else (),
        price_blocks,
        structure,
        gaps,
        inverse_gaps,
        sweeps,
        _overlays(
            swings,
            internal_swings,
            displacements,
            equal_levels,
            reference_levels,
            price_zones,
            price_blocks,
            structure,
            internal_structure,
            gaps,
            inverse_gaps,
            sweeps,
            _closed_at(candles[-1]) if candles else None,
        ),
    )
