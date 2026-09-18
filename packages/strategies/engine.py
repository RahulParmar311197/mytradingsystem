"""Deterministic strategy contracts and initial strategy implementations."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from packages.domain.models import SignalAction
from packages.strategies.regime import LiquidityRegime, RegimeClassification, TrendRegime


@dataclass(frozen=True, slots=True)
class StrategyRequirements:
    timeframes: tuple[str, ...]
    indicators: tuple[str, ...]
    supported_regimes: tuple[TrendRegime, ...]


@dataclass(frozen=True, slots=True)
class StrategyConfig:
    version: str = "1.0.0"
    minimum_relative_volume: Decimal = Decimal("1.2")
    stop_atr_multiple: Decimal = Decimal("1")
    target_risk_multiple: Decimal = Decimal("2")
    maximum_risk_fraction: Decimal = Decimal("0.005")
    mean_reversion_zscore: Decimal = Decimal("2")
    require_orb_retest: bool = False

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("strategy version cannot be empty")
        numeric = (
            self.minimum_relative_volume,
            self.stop_atr_multiple,
            self.target_risk_multiple,
            self.maximum_risk_fraction,
            self.mean_reversion_zscore,
        )
        if any(value <= 0 for value in numeric):
            raise ValueError("strategy numeric parameters must be positive")
        if self.maximum_risk_fraction > Decimal("0.02"):
            raise ValueError("strategy sizing request cannot exceed 2%")


@dataclass(frozen=True, slots=True)
class StrategyContext:
    timestamp: datetime
    instrument_id: UUID
    data_snapshot_id: str
    close: Decimal
    atr: Decimal
    vwap: Decimal
    ema_fast: Decimal
    relative_volume: Decimal
    regime: RegimeClassification
    higher_timeframe_trend: TrendRegime
    session_allowed: bool = True
    liquidity_sweep_direction: SignalAction | None = None
    structure_direction: SignalAction | None = None
    opening_range_high: Decimal | None = None
    opening_range_low: Decimal | None = None
    opening_range_complete: bool = False
    retest_confirmed: bool = False
    fvg_direction: SignalAction | None = None
    fvg_lower: Decimal | None = None
    fvg_upper: Decimal | None = None
    zscore: Decimal | None = None

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("strategy timestamp must be timezone-aware")
        if not self.data_snapshot_id.strip():
            raise ValueError("data_snapshot_id cannot be empty")
        if any(value <= 0 for value in (self.close, self.atr, self.vwap, self.ema_fast)):
            raise ValueError("strategy prices and ATR must be positive")
        if self.relative_volume < 0:
            raise ValueError("relative volume cannot be negative")
        if (self.opening_range_high is None) != (self.opening_range_low is None):
            raise ValueError("opening range high and low must be supplied together")
        if (
            self.opening_range_high is not None
            and self.opening_range_low is not None
            and self.opening_range_high <= self.opening_range_low
        ):
            raise ValueError("opening range high must exceed low")
        if (self.fvg_lower is None) != (self.fvg_upper is None):
            raise ValueError("FVG bounds must be supplied together")
        if (
            self.fvg_lower is not None
            and self.fvg_upper is not None
            and self.fvg_upper <= self.fvg_lower
        ):
            raise ValueError("FVG upper bound must exceed lower bound")


@dataclass(frozen=True, slots=True)
class StrategySignal:
    timestamp: datetime
    instrument_id: UUID
    strategy: str
    strategy_version: str
    action: SignalAction
    confidence: Decimal
    contributing_factors: dict[str, Decimal | str | bool]
    rejection_reasons: tuple[str, ...]
    proposed_entry: Decimal | None
    proposed_stop: Decimal | None
    proposed_targets: tuple[Decimal, ...]
    requested_risk_fraction: Decimal
    expiry: datetime | None
    explanation: str
    data_snapshot_id: str


class Strategy(Protocol):
    name: str
    requirements: StrategyRequirements

    def evaluate(self, context: StrategyContext) -> StrategySignal: ...


class _BaseStrategy:
    name = "base"
    requirements = StrategyRequirements((), (), ())

    def __init__(self, config: StrategyConfig | None = None) -> None:
        self.config = config or StrategyConfig()

    def _gate(self, context: StrategyContext) -> tuple[str, ...]:
        reasons: list[str] = []
        if not context.session_allowed:
            reasons.append("OUTSIDE_TRADING_SESSION")
        if not context.regime.strategy_entries_permitted:
            reasons.append("EVENT_RISK_LOCK")
        if context.regime.liquidity is LiquidityRegime.LOW_LIQUIDITY:
            reasons.append("LOW_LIQUIDITY")
        if context.regime.trend not in self.requirements.supported_regimes:
            reasons.append("UNSUPPORTED_REGIME")
        return tuple(reasons)

    def _no_trade(self, context: StrategyContext, *reasons: str) -> StrategySignal:
        return StrategySignal(
            context.timestamp.astimezone(UTC),
            context.instrument_id,
            self.name,
            self.config.version,
            SignalAction.NO_TRADE,
            Decimal(0),
            {"regime": context.regime.trend.value},
            tuple(reasons),
            None,
            None,
            (),
            Decimal(0),
            None,
            f"No trade: {', '.join(reasons)}",
            context.data_snapshot_id,
        )

    def _signal(
        self,
        context: StrategyContext,
        action: SignalAction,
        confidence: Decimal,
        stop: Decimal,
        target: Decimal,
        factors: dict[str, Decimal | str | bool],
        explanation: str,
    ) -> StrategySignal:
        return StrategySignal(
            context.timestamp.astimezone(UTC),
            context.instrument_id,
            self.name,
            self.config.version,
            action,
            min(Decimal(1), max(Decimal(0), confidence)),
            factors,
            (),
            context.close,
            stop,
            (target,),
            self.config.maximum_risk_fraction,
            None,
            explanation,
            context.data_snapshot_id,
        )

    def _levels(self, context: StrategyContext, action: SignalAction) -> tuple[Decimal, Decimal]:
        risk = context.atr * self.config.stop_atr_multiple
        if action is SignalAction.LONG:
            return context.close - risk, context.close + risk * self.config.target_risk_multiple
        return context.close + risk, context.close - risk * self.config.target_risk_multiple


class TrendContinuationStrategy(_BaseStrategy):
    name = "trend_continuation"
    requirements = StrategyRequirements(
        ("5m", "15m", "1h"),
        ("EMA", "VWAP", "ATR", "relative_volume", "external_structure"),
        (TrendRegime.BULL_TREND, TrendRegime.BEAR_TREND),
    )

    def evaluate(self, context: StrategyContext) -> StrategySignal:
        if reasons := self._gate(context):
            return self._no_trade(context, *reasons)
        bullish = (
            context.regime.trend is TrendRegime.BULL_TREND
            and context.higher_timeframe_trend is TrendRegime.BULL_TREND
            and context.close >= context.ema_fast
            and context.close >= context.vwap
        )
        bearish = (
            context.regime.trend is TrendRegime.BEAR_TREND
            and context.higher_timeframe_trend is TrendRegime.BEAR_TREND
            and context.close <= context.ema_fast
            and context.close <= context.vwap
        )
        if context.relative_volume < self.config.minimum_relative_volume:
            return self._no_trade(context, "INSUFFICIENT_VOLUME_CONFIRMATION")
        if not bullish and not bearish:
            return self._no_trade(context, "TREND_ALIGNMENT_FAILED")
        action = SignalAction.LONG if bullish else SignalAction.SHORT
        stop, target = self._levels(context, action)
        return self._signal(
            context,
            action,
            Decimal("0.75"),
            stop,
            target,
            {"relative_volume": context.relative_volume, "higher_timeframe_aligned": True},
            "Higher-timeframe trend, EMA, VWAP, and volume are aligned",
        )


class LiquiditySweepReversalStrategy(_BaseStrategy):
    name = "liquidity_sweep_reversal"
    requirements = StrategyRequirements(
        ("5m", "15m"),
        ("liquidity_sweep", "market_structure", "ATR"),
        (TrendRegime.BULL_TREND, TrendRegime.BEAR_TREND, TrendRegime.RANGE),
    )

    def evaluate(self, context: StrategyContext) -> StrategySignal:
        if reasons := self._gate(context):
            return self._no_trade(context, *reasons)
        direction = context.liquidity_sweep_direction
        if direction not in (SignalAction.LONG, SignalAction.SHORT):
            return self._no_trade(context, "NO_CONFIRMED_LIQUIDITY_SWEEP")
        if context.structure_direction is not direction:
            return self._no_trade(context, "STRUCTURE_CONFIRMATION_MISSING")
        stop, target = self._levels(context, direction)
        return self._signal(
            context,
            direction,
            Decimal("0.7"),
            stop,
            target,
            {"sweep": direction.value, "structure_confirmed": True},
            "Liquidity sweep rejected and structure confirmed the reversal",
        )


class OpeningRangeBreakoutStrategy(_BaseStrategy):
    name = "opening_range_breakout"
    requirements = StrategyRequirements(
        ("1m", "5m"),
        ("opening_range", "relative_volume", "ATR"),
        (TrendRegime.BULL_TREND, TrendRegime.BEAR_TREND, TrendRegime.RANGE),
    )

    def evaluate(self, context: StrategyContext) -> StrategySignal:
        if reasons := self._gate(context):
            return self._no_trade(context, *reasons)
        if (
            not context.opening_range_complete
            or context.opening_range_high is None
            or context.opening_range_low is None
        ):
            return self._no_trade(context, "OPENING_RANGE_INCOMPLETE")
        if context.relative_volume < self.config.minimum_relative_volume:
            return self._no_trade(context, "INSUFFICIENT_VOLUME_CONFIRMATION")
        if self.config.require_orb_retest and not context.retest_confirmed:
            return self._no_trade(context, "RETEST_REQUIRED")
        if context.close > context.opening_range_high:
            action = SignalAction.LONG
        elif context.close < context.opening_range_low:
            action = SignalAction.SHORT
        else:
            return self._no_trade(context, "NO_OPENING_RANGE_BREAKOUT")
        stop, target = self._levels(context, action)
        return self._signal(
            context,
            action,
            Decimal("0.7"),
            stop,
            target,
            {
                "relative_volume": context.relative_volume,
                "retest_confirmed": context.retest_confirmed,
            },
            "Closed outside the completed opening range with volume confirmation",
        )


class FairValueGapContinuationStrategy(_BaseStrategy):
    name = "fvg_continuation"
    requirements = StrategyRequirements(
        ("5m", "15m", "1h"),
        ("fair_value_gap", "external_structure", "ATR"),
        (TrendRegime.BULL_TREND, TrendRegime.BEAR_TREND),
    )

    def evaluate(self, context: StrategyContext) -> StrategySignal:
        if reasons := self._gate(context):
            return self._no_trade(context, *reasons)
        direction = context.fvg_direction
        if (
            direction not in (SignalAction.LONG, SignalAction.SHORT)
            or context.fvg_lower is None
            or context.fvg_upper is None
        ):
            return self._no_trade(context, "NO_ACTIVE_FVG")
        trend = TrendRegime.BULL_TREND if direction is SignalAction.LONG else TrendRegime.BEAR_TREND
        if context.regime.trend is not trend or context.higher_timeframe_trend is not trend:
            return self._no_trade(context, "FVG_TREND_MISMATCH")
        if not context.fvg_lower <= context.close <= context.fvg_upper:
            return self._no_trade(context, "PRICE_OUTSIDE_FVG")
        stop, target = self._levels(context, direction)
        return self._signal(
            context,
            direction,
            Decimal("0.7"),
            stop,
            target,
            {"fvg_lower": context.fvg_lower, "fvg_upper": context.fvg_upper},
            "Price retraced into an active FVG aligned with higher-timeframe trend",
        )


class RangeMeanReversionStrategy(_BaseStrategy):
    name = "range_mean_reversion"
    requirements = StrategyRequirements(
        ("5m", "15m"),
        ("zscore", "VWAP", "ATR"),
        (TrendRegime.RANGE,),
    )

    def evaluate(self, context: StrategyContext) -> StrategySignal:
        if reasons := self._gate(context):
            return self._no_trade(context, *reasons)
        if context.zscore is None:
            return self._no_trade(context, "ZSCORE_UNAVAILABLE")
        if context.zscore <= -self.config.mean_reversion_zscore:
            action = SignalAction.LONG
        elif context.zscore >= self.config.mean_reversion_zscore:
            action = SignalAction.SHORT
        else:
            return self._no_trade(context, "MEAN_REVERSION_THRESHOLD_NOT_MET")
        stop, _ = self._levels(context, action)
        return self._signal(
            context,
            action,
            Decimal("0.65"),
            stop,
            context.vwap,
            {"zscore": context.zscore, "target_vwap": context.vwap},
            "Extreme range z-score targets reversion to VWAP",
        )
