"""Transparent, point-in-time market-regime classification."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum


class TrendRegime(StrEnum):
    BULL_TREND = "bull_trend"
    BEAR_TREND = "bear_trend"
    RANGE = "range"


class VolatilityRegime(StrEnum):
    HIGH_VOLATILITY = "high_volatility"
    NORMAL_VOLATILITY = "normal_volatility"
    LOW_VOLATILITY = "low_volatility"


class LiquidityRegime(StrEnum):
    HIGH_LIQUIDITY = "high_liquidity"
    NORMAL_LIQUIDITY = "normal_liquidity"
    LOW_LIQUIDITY = "low_liquidity"


@dataclass(frozen=True, slots=True)
class RegimeConfig:
    adx_trend_threshold: Decimal = Decimal("20")
    high_atr_percent: Decimal = Decimal("2")
    low_atr_percent: Decimal = Decimal("0.5")
    high_liquidity_relative_volume: Decimal = Decimal("1.2")
    low_liquidity_relative_volume: Decimal = Decimal("0.7")
    high_liquidity_max_spread_bps: Decimal = Decimal("10")
    low_liquidity_spread_bps: Decimal = Decimal("25")
    rule_version: str = "regime-rules-v1"

    def __post_init__(self) -> None:
        numeric = (
            self.adx_trend_threshold,
            self.high_atr_percent,
            self.low_atr_percent,
            self.high_liquidity_relative_volume,
            self.low_liquidity_relative_volume,
            self.high_liquidity_max_spread_bps,
            self.low_liquidity_spread_bps,
        )
        if any(value < 0 for value in numeric):
            raise ValueError("regime thresholds cannot be negative")
        if self.low_atr_percent >= self.high_atr_percent:
            raise ValueError("low ATR threshold must be below high ATR threshold")
        if self.low_liquidity_relative_volume >= self.high_liquidity_relative_volume:
            raise ValueError("low relative-volume threshold must be below high threshold")
        if self.high_liquidity_max_spread_bps >= self.low_liquidity_spread_bps:
            raise ValueError("high-liquidity spread must be below low-liquidity spread")
        if not self.rule_version.strip():
            raise ValueError("rule_version cannot be empty")


@dataclass(frozen=True, slots=True)
class RegimeFeatures:
    """Features available at ``timestamp``; no raw future series are accepted."""

    timestamp: datetime
    close: Decimal
    ema_fast: Decimal
    ema_slow: Decimal
    adx: Decimal
    atr_percent: Decimal
    relative_volume: Decimal
    spread_bps: Decimal
    event_risk: bool = False

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("regime timestamp must be timezone-aware")
        if self.close <= 0 or self.ema_fast <= 0 or self.ema_slow <= 0:
            raise ValueError("prices and moving averages must be positive")
        if any(
            value < 0
            for value in (self.adx, self.atr_percent, self.relative_volume, self.spread_bps)
        ):
            raise ValueError("regime features cannot be negative")


@dataclass(frozen=True, slots=True)
class RegimeClassification:
    timestamp: datetime
    trend: TrendRegime
    volatility: VolatilityRegime
    liquidity: LiquidityRegime
    event_risk: bool
    confidence: Decimal
    supporting_features: dict[str, Decimal | bool | str]
    rule_version: str

    @property
    def strategy_entries_permitted(self) -> bool:
        """Event risk is an explicit entry lock, not a hidden regime override."""
        return not self.event_risk


def _bounded(value: Decimal) -> Decimal:
    return max(Decimal(0), min(Decimal(1), value))


def _trend(features: RegimeFeatures, config: RegimeConfig) -> tuple[TrendRegime, Decimal]:
    separation = abs(features.ema_fast - features.ema_slow) / features.close
    strength = _bounded(features.adx / max(config.adx_trend_threshold, Decimal("0.0001")))
    confidence = _bounded(Decimal("0.5") + separation * 100 + strength / 4)
    if features.adx >= config.adx_trend_threshold:
        if features.close > features.ema_fast > features.ema_slow:
            return TrendRegime.BULL_TREND, confidence
        if features.close < features.ema_fast < features.ema_slow:
            return TrendRegime.BEAR_TREND, confidence
    range_confidence = _bounded(Decimal(1) - strength / 2)
    return TrendRegime.RANGE, range_confidence


def _volatility(features: RegimeFeatures, config: RegimeConfig) -> tuple[VolatilityRegime, Decimal]:
    if features.atr_percent >= config.high_atr_percent:
        return (
            VolatilityRegime.HIGH_VOLATILITY,
            _bounded(features.atr_percent / config.high_atr_percent / 2 + Decimal("0.5")),
        )
    if features.atr_percent <= config.low_atr_percent:
        return (
            VolatilityRegime.LOW_VOLATILITY,
            _bounded(
                Decimal(1)
                - features.atr_percent / max(config.low_atr_percent, Decimal("0.0001")) / 2
            ),
        )
    midpoint = (config.high_atr_percent + config.low_atr_percent) / 2
    half_width = (config.high_atr_percent - config.low_atr_percent) / 2
    return (
        VolatilityRegime.NORMAL_VOLATILITY,
        _bounded(Decimal(1) - abs(features.atr_percent - midpoint) / half_width / 2),
    )


def _liquidity(features: RegimeFeatures, config: RegimeConfig) -> tuple[LiquidityRegime, Decimal]:
    if (
        features.relative_volume >= config.high_liquidity_relative_volume
        and features.spread_bps <= config.high_liquidity_max_spread_bps
    ):
        volume_score = features.relative_volume / config.high_liquidity_relative_volume
        spread_score = Decimal(1) - features.spread_bps / max(
            config.low_liquidity_spread_bps, Decimal("0.0001")
        )
        return LiquidityRegime.HIGH_LIQUIDITY, _bounded((volume_score + spread_score) / 2)
    if (
        features.relative_volume <= config.low_liquidity_relative_volume
        or features.spread_bps >= config.low_liquidity_spread_bps
    ):
        volume_deficit = _bounded(
            Decimal(1)
            - features.relative_volume
            / max(config.low_liquidity_relative_volume, Decimal("0.0001"))
        )
        spread_excess = _bounded(
            features.spread_bps / max(config.low_liquidity_spread_bps, Decimal("0.0001"))
            - Decimal(1)
        )
        return (
            LiquidityRegime.LOW_LIQUIDITY,
            _bounded(Decimal("0.5") + max(volume_deficit, spread_excess) / 2),
        )
    return LiquidityRegime.NORMAL_LIQUIDITY, Decimal("0.6")


def classify_regime(
    features: RegimeFeatures, config: RegimeConfig | None = None
) -> RegimeClassification:
    """Classify independent regime axes from one point-in-time feature snapshot."""
    rules = config or RegimeConfig()
    trend, trend_confidence = _trend(features, rules)
    volatility, volatility_confidence = _volatility(features, rules)
    liquidity, liquidity_confidence = _liquidity(features, rules)
    confidence = (trend_confidence + volatility_confidence + liquidity_confidence) / 3
    return RegimeClassification(
        features.timestamp.astimezone(UTC),
        trend,
        volatility,
        liquidity,
        features.event_risk,
        confidence,
        {
            "close": features.close,
            "ema_fast": features.ema_fast,
            "ema_slow": features.ema_slow,
            "adx": features.adx,
            "atr_percent": features.atr_percent,
            "relative_volume": features.relative_volume,
            "spread_bps": features.spread_bps,
            "event_risk": features.event_risk,
            "trend_rule": trend.value,
        },
        rules.rule_version,
    )
