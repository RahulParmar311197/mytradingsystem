from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from packages.domain.models import Candle
from packages.smc_ict import (
    BlockKind,
    BlockStatus,
    Direction,
    GapStatus,
    KillZone,
    LiquiditySide,
    SMCConfig,
    StructureKind,
    StructureScope,
    ZoneKind,
    active_kill_zones,
    analyze,
)

INSTRUMENT = uuid4()
START = datetime(2026, 9, 18, 4, tzinfo=UTC)


def candles(rows: list[tuple[str, str, str, str]]) -> tuple[Candle, ...]:
    return tuple(
        Candle(
            instrument_id=INSTRUMENT,
            timestamp=START + timedelta(minutes=index),
            timeframe_seconds=60,
            open=Decimal(open_),
            high=Decimal(high),
            low=Decimal(low),
            close=Decimal(close),
            volume=Decimal("100"),
        )
        for index, (open_, high, low, close) in enumerate(rows)
    )


def closed_at(candle: Candle) -> datetime:
    return candle.timestamp + timedelta(seconds=candle.timeframe_seconds)


def test_swing_is_published_only_at_confirmation_candle() -> None:
    source = candles([("9", "10", "8", "9"), ("10", "12", "9", "11"), ("10", "11", "9", "10")])
    rules = SMCConfig(swing_left=1, swing_right=1)
    assert analyze(source[:2], rules).swings == ()
    result = analyze(source, rules)
    assert len(result.swings) == 1
    swing = result.swings[0]
    assert swing.direction is Direction.BEARISH
    assert swing.candle_timestamp == source[1].timestamp
    assert swing.confirmed_at == closed_at(source[2])
    assert swing.evidence == tuple(item.timestamp for item in source)


def test_fair_value_gap_has_evidence_invalidation_and_overlay() -> None:
    source = candles(
        [("99", "100", "98", "99"), ("100", "104", "99", "103"), ("103", "105", "102", "104")]
    )
    result = analyze(source, SMCConfig(swing_left=1, swing_right=1))
    assert len(result.fair_value_gaps) == 1
    gap = result.fair_value_gaps[0]
    assert (gap.direction, gap.lower, gap.upper) == (
        Direction.BULLISH,
        Decimal("100"),
        Decimal("102"),
    )
    assert gap.detected_at == closed_at(source[2])
    assert gap.consequent_encroachment == Decimal("101")
    assert gap.status is GapStatus.ACTIVE
    assert "at or below 100" in gap.invalidation
    overlay = next(item for item in result.overlays if item.kind == "fair_value_gap")
    assert (overlay.lower, overlay.upper, overlay.end) == (gap.lower, gap.upper, gap.detected_at)


def test_gap_lifecycle_is_point_in_time_and_close_through_creates_inverse_gap() -> None:
    source = candles(
        [
            ("99", "100", "98", "99"),
            ("100", "104", "99", "103"),
            ("103", "105", "102", "104"),
            ("103", "104", "101", "103"),
            ("101", "102", "99", "99.5"),
        ]
    )
    rules = SMCConfig(swing_left=1, swing_right=1, minimum_gap_percent=Decimal("0.5"))

    active = analyze(source[:3], rules).fair_value_gaps[0]
    assert (active.status, active.mitigated_at, active.invalidated_at) == (
        GapStatus.ACTIVE,
        None,
        None,
    )

    mitigated = analyze(source[:4], rules).fair_value_gaps[0]
    assert mitigated.status is GapStatus.MITIGATED
    assert mitigated.mitigated_at == closed_at(source[3])
    assert mitigated.invalidated_at is None
    assert analyze(source[:4], rules).inverse_fair_value_gaps == ()

    result = analyze(source, rules)
    invalidated = result.fair_value_gaps[0]
    assert invalidated.status is GapStatus.INVALIDATED
    assert invalidated.invalidated_at == closed_at(source[4])
    inverse = result.inverse_fair_value_gaps[0]
    assert inverse.direction is Direction.BEARISH
    assert (inverse.lower, inverse.upper) == (Decimal("100"), Decimal("102"))
    assert inverse.detected_at == closed_at(source[4])
    assert inverse.evidence[-1] == source[4].timestamp
    assert any(item.kind == "inverse_fair_value_gap" for item in result.overlays)


def test_close_break_and_wick_sweep_are_distinct() -> None:
    base = candles(
        [
            ("9", "10", "8", "9"),
            ("10", "12", "9", "11"),
            ("10", "11", "9", "10"),
            ("11", "13", "10", "11.5"),
            ("11", "12.5", "10", "12.2"),
        ]
    )
    rules = SMCConfig(swing_left=1, swing_right=1, minimum_gap_percent=Decimal("99"))
    swept = analyze(base[:-1], rules)
    assert len(swept.liquidity_sweeps) == 1
    assert swept.liquidity_sweeps[0].level == Decimal("12")
    assert swept.liquidity_sweeps[0].direction is Direction.BEARISH
    assert swept.structure == ()
    broken = analyze(base, rules)
    assert len(broken.structure) == 1
    assert broken.structure[0].direction is Direction.BULLISH
    assert broken.structure[0].level == Decimal("12")
    assert "12.2 closed beyond" in broken.structure[0].explanation


def test_displacement_requires_large_body_and_directional_close() -> None:
    source = candles([("10", "12", "9", "11"), ("11", "13", "10", "12"), ("10", "15", "9", "14")])
    rules = SMCConfig(
        swing_left=1,
        swing_right=1,
        displacement_lookback=2,
        displacement_body_multiple=Decimal("2"),
        displacement_close_location=Decimal("0.75"),
    )
    assert analyze(source[:2], rules).displacements == ()
    displacement = analyze(source, rules).displacements[0]
    assert displacement.direction is Direction.BULLISH
    assert displacement.body == Decimal("4")
    assert displacement.average_prior_body == Decimal("1")
    assert displacement.close_location == Decimal("0.8333333333333333333333333333")
    assert displacement.evidence == tuple(item.timestamp for item in source)


def test_equal_highs_are_available_only_after_both_swings_are_confirmed() -> None:
    source = candles(
        [
            ("9", "10", "8", "9"),
            ("10", "12", "9", "11"),
            ("9.5", "10", "9", "9.5"),
            ("10", "12.005", "9", "11"),
            ("9.5", "10", "9", "9.5"),
        ]
    )
    rules = SMCConfig(swing_left=1, swing_right=1, equal_level_tolerance_percent=Decimal("0.1"))
    assert analyze(source[:-1], rules).equal_levels == ()
    level = analyze(source, rules).equal_levels[0]
    assert level.side is LiquiditySide.BUY_SIDE
    assert (level.lower, level.upper) == (Decimal("12"), Decimal("12.005"))
    assert level.detected_at == closed_at(source[4])


def test_mss_requires_choch_and_same_candle_displacement() -> None:
    source = candles(
        [
            ("9", "10", "8", "9"),
            ("10", "12", "9", "11"),
            ("10", "11", "8.5", "9"),
            ("11", "13", "10", "12.5"),
            ("11", "12", "9", "10"),
            ("10", "11", "9.5", "10"),
            ("10", "10.2", "7", "7.5"),
        ]
    )
    rules = SMCConfig(
        swing_left=1,
        swing_right=1,
        displacement_lookback=2,
        displacement_body_multiple=Decimal("2"),
        displacement_close_location=Decimal("0.75"),
        minimum_gap_percent=Decimal("99"),
    )
    result = analyze(source, rules)
    kinds = [item.kind for item in result.structure]
    assert StructureKind.BREAK_OF_STRUCTURE in kinds
    assert StructureKind.CHANGE_OF_CHARACTER in kinds
    assert StructureKind.MARKET_STRUCTURE_SHIFT in kinds
    mss = next(
        item for item in result.structure if item.kind is StructureKind.MARKET_STRUCTURE_SHIFT
    )
    assert mss.detected_at == closed_at(source[6])
    assert mss.direction is Direction.BEARISH


def test_internal_and_external_structure_have_independent_confirmation_windows() -> None:
    source = candles(
        [
            ("9", "10", "8", "9"),
            ("10", "12", "9", "11"),
            ("10", "11", "9.5", "10"),
            ("11", "13", "10", "12"),
            ("11", "12", "10.5", "11"),
            ("11", "14", "10.5", "13.5"),
        ]
    )
    rules = SMCConfig(
        swing_left=2,
        swing_right=2,
        internal_swing_left=1,
        internal_swing_right=1,
        displacement_lookback=2,
        displacement_body_multiple=Decimal("2"),
    )
    result = analyze(source, rules)
    assert result.swings == ()
    assert result.structure == ()
    assert result.price_blocks == ()
    assert result.internal_swings
    assert all(item.scope is StructureScope.INTERNAL for item in result.internal_swings)
    assert len(result.internal_structure) == 1
    event = result.internal_structure[0]
    assert event.scope is StructureScope.INTERNAL
    assert event.kind is StructureKind.BREAK_OF_STRUCTURE
    assert event.level == Decimal("13")
    assert event.detected_at == closed_at(source[5])
    assert any(item.label == "internal break of structure" for item in result.overlays)


def test_order_block_lifecycle_emits_mitigation_and_breaker_without_lookahead() -> None:
    source = candles(
        [
            ("9", "10", "8", "9"),
            ("10", "12", "9", "11"),
            ("10", "11", "8.5", "9"),
            ("11", "13", "10", "12.5"),
            ("11", "12", "9", "10"),
            ("10", "11", "9.5", "10"),
            ("10", "10.2", "7", "7.5"),
            ("10", "11", "9", "10"),
            ("12", "15", "11", "14"),
        ]
    )
    rules = SMCConfig(
        swing_left=1,
        swing_right=1,
        displacement_lookback=2,
        displacement_body_multiple=Decimal("2"),
        displacement_close_location=Decimal("0.75"),
        order_block_lookback=4,
        minimum_gap_percent=Decimal("99"),
    )
    at_break = analyze(source[:7], rules)
    order = next(item for item in at_break.price_blocks if item.kind is BlockKind.ORDER_BLOCK)
    assert order.direction is Direction.BEARISH
    assert (order.lower, order.upper) == (Decimal("10"), Decimal("13"))
    assert order.origin_timestamp == source[3].timestamp
    assert order.status is BlockStatus.ACTIVE
    assert order.mitigated_at is None

    at_retest = analyze(source[:8], rules)
    order = next(item for item in at_retest.price_blocks if item.kind is BlockKind.ORDER_BLOCK)
    mitigation = next(
        item for item in at_retest.price_blocks if item.kind is BlockKind.MITIGATION_BLOCK
    )
    assert order.status is BlockStatus.MITIGATED
    assert order.mitigated_at == closed_at(source[7])
    assert mitigation.detected_at == closed_at(source[7])
    assert not any(item.kind is BlockKind.BREAKER_BLOCK for item in at_retest.price_blocks)

    invalidated = analyze(source, rules)
    order = next(item for item in invalidated.price_blocks if item.kind is BlockKind.ORDER_BLOCK)
    breaker = next(
        item for item in invalidated.price_blocks if item.kind is BlockKind.BREAKER_BLOCK
    )
    assert order.status is BlockStatus.INVALIDATED
    assert order.invalidated_at == closed_at(source[8])
    assert breaker.direction is Direction.BULLISH
    assert breaker.detected_at == closed_at(source[8])
    assert breaker.evidence[-1] == source[8].timestamp


def test_reference_levels_use_only_completed_prior_ist_periods() -> None:
    india = ZoneInfo("Asia/Kolkata")
    timestamps = [
        datetime(2026, 9, 11, 9, 15, tzinfo=india),
        datetime(2026, 9, 14, 9, 15, tzinfo=india),
        datetime(2026, 9, 15, 9, 15, tzinfo=india),
    ]
    source = tuple(
        Candle(
            instrument_id=INSTRUMENT,
            timestamp=timestamp,
            timeframe_seconds=60,
            open=Decimal("100"),
            high=high,
            low=low,
            close=Decimal("100"),
            volume=Decimal("100"),
        )
        for timestamp, high, low in zip(
            timestamps,
            (Decimal("110"), Decimal("105"), Decimal("108")),
            (Decimal("90"), Decimal("95"), Decimal("94")),
            strict=True,
        )
    )
    levels = {item.kind.value: item for item in analyze(source).reference_levels}
    assert levels["previous_day_high"].price == Decimal("105")
    assert levels["previous_day_low"].price == Decimal("95")
    assert levels["previous_week_high"].price == Decimal("110")
    assert levels["previous_week_low"].price == Decimal("90")
    assert levels["session_high"].price == Decimal("108")
    assert levels["previous_day_high"].available_at == source[1].timestamp + timedelta(minutes=1)


def test_confirmed_dealing_range_produces_premium_discount_and_ote() -> None:
    source = candles(
        [
            ("10", "11", "9", "10"),
            ("9", "10", "8", "9"),
            ("10", "11", "9", "10"),
            ("12", "14", "10", "13"),
            ("11", "12", "9", "10"),
        ]
    )
    result = analyze(source, SMCConfig(swing_left=1, swing_right=1))
    zones = {item.kind: item for item in result.price_zones}
    assert (zones[ZoneKind.DISCOUNT].lower, zones[ZoneKind.DISCOUNT].upper) == (
        Decimal("8"),
        Decimal("11"),
    )
    assert (zones[ZoneKind.PREMIUM].lower, zones[ZoneKind.PREMIUM].upper) == (
        Decimal("11"),
        Decimal("14"),
    )
    assert (zones[ZoneKind.BULLISH_OTE].lower, zones[ZoneKind.BULLISH_OTE].upper) == (
        Decimal("11.72"),
        Decimal("12.74"),
    )
    assert zones[ZoneKind.PREMIUM].available_at == closed_at(source[4])


def test_kill_zones_use_aware_half_open_local_windows() -> None:
    india = ZoneInfo("Asia/Kolkata")
    assert "nse_open" in active_kill_zones(datetime(2026, 9, 18, 9, 15, tzinfo=india))
    assert "nse_open" not in active_kill_zones(datetime(2026, 9, 18, 10, 15, tzinfo=india))
    overnight = (KillZone("overnight", time(22), time(2), "Asia/Kolkata"),)
    assert active_kill_zones(datetime(2026, 9, 18, 23, tzinfo=india), overnight) == ("overnight",)
    with pytest.raises(ValueError, match="timezone-aware"):
        active_kill_zones(datetime(2026, 9, 18, 9, 15))


def test_analysis_rejects_open_or_out_of_order_data() -> None:
    source = candles([("9", "10", "8", "9"), ("10", "11", "9", "10")])
    with pytest.raises(ValueError, match="strictly increasing"):
        analyze(tuple(reversed(source)))
    open_candle = source[0].model_copy(update={"is_closed": False})
    with pytest.raises(ValueError, match="closed candles only"):
        analyze((open_candle,))


def test_configuration_rejects_subjective_or_invalid_thresholds() -> None:
    with pytest.raises(ValueError, match="positive"):
        SMCConfig(swing_left=0)
    with pytest.raises(ValueError, match="cannot be negative"):
        SMCConfig(minimum_gap_percent=Decimal("-0.1"))
