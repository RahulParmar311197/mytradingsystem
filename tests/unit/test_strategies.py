from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from packages.domain.models import SignalAction
from packages.strategies import (
    FairValueGapContinuationStrategy,
    LiquidityRegime,
    LiquiditySweepReversalStrategy,
    OpeningRangeBreakoutStrategy,
    RangeMeanReversionStrategy,
    RegimeClassification,
    StrategyConfig,
    StrategyContext,
    TrendContinuationStrategy,
    TrendRegime,
    VolatilityRegime,
)

NOW = datetime(2026, 9, 18, 10, tzinfo=UTC)


def regime(trend: TrendRegime, *, event_risk: bool = False) -> RegimeClassification:
    return RegimeClassification(
        NOW,
        trend,
        VolatilityRegime.NORMAL_VOLATILITY,
        LiquidityRegime.HIGH_LIQUIDITY,
        event_risk,
        Decimal("0.8"),
        {"fixture": True},
        "regime-rules-v1",
    )


def context(trend: TrendRegime = TrendRegime.BULL_TREND) -> StrategyContext:
    return StrategyContext(
        timestamp=NOW,
        instrument_id=uuid4(),
        data_snapshot_id="snapshot-1",
        close=Decimal("105"),
        atr=Decimal("2"),
        vwap=Decimal("103"),
        ema_fast=Decimal("104"),
        relative_volume=Decimal("1.5"),
        regime=regime(trend),
        higher_timeframe_trend=trend,
    )


def test_trend_continuation_returns_sizing_request_not_order() -> None:
    strategy = TrendContinuationStrategy()
    result = strategy.evaluate(context())
    assert result.action is SignalAction.LONG
    assert (result.proposed_entry, result.proposed_stop, result.proposed_targets) == (
        Decimal("105"),
        Decimal("103"),
        (Decimal("109"),),
    )
    assert result.requested_risk_fraction == Decimal("0.005")
    assert "1h" in strategy.requirements.timeframes
    assert result.rejection_reasons == ()


def test_liquidity_sweep_requires_matching_structure_confirmation() -> None:
    strategy = LiquiditySweepReversalStrategy()
    base = replace(context(TrendRegime.RANGE), liquidity_sweep_direction=SignalAction.SHORT)
    rejected = strategy.evaluate(base)
    assert rejected.action is SignalAction.NO_TRADE
    assert rejected.rejection_reasons == ("STRUCTURE_CONFIRMATION_MISSING",)
    accepted = strategy.evaluate(replace(base, structure_direction=SignalAction.SHORT))
    assert accepted.action is SignalAction.SHORT


def test_opening_range_breakout_supports_optional_retest_gate() -> None:
    strategy = OpeningRangeBreakoutStrategy(StrategyConfig(require_orb_retest=True))
    base = replace(
        context(TrendRegime.RANGE),
        opening_range_high=Decimal("104"),
        opening_range_low=Decimal("100"),
        opening_range_complete=True,
    )
    assert strategy.evaluate(base).rejection_reasons == ("RETEST_REQUIRED",)
    accepted = strategy.evaluate(replace(base, retest_confirmed=True))
    assert accepted.action is SignalAction.LONG


def test_fvg_continuation_requires_active_zone_and_trend_alignment() -> None:
    strategy = FairValueGapContinuationStrategy()
    base = replace(
        context(),
        close=Decimal("104"),
        fvg_direction=SignalAction.LONG,
        fvg_lower=Decimal("103"),
        fvg_upper=Decimal("105"),
    )
    assert strategy.evaluate(base).action is SignalAction.LONG
    mismatch = replace(base, higher_timeframe_trend=TrendRegime.BEAR_TREND)
    assert strategy.evaluate(mismatch).rejection_reasons == ("FVG_TREND_MISMATCH",)


def test_mean_reversion_is_restricted_to_range_and_targets_vwap() -> None:
    strategy = RangeMeanReversionStrategy()
    accepted = strategy.evaluate(replace(context(TrendRegime.RANGE), zscore=Decimal("-2.2")))
    assert accepted.action is SignalAction.LONG
    assert accepted.proposed_targets == (Decimal("103"),)
    rejected = strategy.evaluate(replace(context(), zscore=Decimal("-2.2")))
    assert rejected.action is SignalAction.NO_TRADE
    assert rejected.rejection_reasons == ("UNSUPPORTED_REGIME",)


def test_event_risk_and_session_gates_produce_common_no_trade() -> None:
    locked = replace(context(), regime=regime(TrendRegime.BULL_TREND, event_risk=True))
    result = TrendContinuationStrategy().evaluate(locked)
    assert result.action is SignalAction.NO_TRADE
    assert result.rejection_reasons == ("EVENT_RISK_LOCK",)
    outside = TrendContinuationStrategy().evaluate(replace(context(), session_allowed=False))
    assert outside.rejection_reasons == ("OUTSIDE_TRADING_SESSION",)
