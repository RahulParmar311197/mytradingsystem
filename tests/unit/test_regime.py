from datetime import UTC, datetime
from decimal import Decimal

import pytest

from packages.strategies import (
    LiquidityRegime,
    RegimeConfig,
    RegimeFeatures,
    TrendRegime,
    VolatilityRegime,
    classify_regime,
)

NOW = datetime(2026, 9, 18, 10, tzinfo=UTC)


def features(**changes: object) -> RegimeFeatures:
    values: dict[str, object] = {
        "timestamp": NOW,
        "close": Decimal("105"),
        "ema_fast": Decimal("103"),
        "ema_slow": Decimal("100"),
        "adx": Decimal("25"),
        "atr_percent": Decimal("1"),
        "relative_volume": Decimal("1.5"),
        "spread_bps": Decimal("5"),
    }
    values.update(changes)
    return RegimeFeatures(**values)  # type: ignore[arg-type]


def test_classifies_bull_normal_volatility_high_liquidity_with_evidence() -> None:
    result = classify_regime(features())
    assert result.trend is TrendRegime.BULL_TREND
    assert result.volatility is VolatilityRegime.NORMAL_VOLATILITY
    assert result.liquidity is LiquidityRegime.HIGH_LIQUIDITY
    assert Decimal(0) <= result.confidence <= Decimal(1)
    assert result.supporting_features["adx"] == Decimal("25")
    assert result.rule_version == "regime-rules-v1"
    assert result.strategy_entries_permitted is True


def test_bear_high_volatility_low_liquidity_and_event_lock_are_independent() -> None:
    result = classify_regime(
        features(
            close=Decimal("95"),
            ema_fast=Decimal("97"),
            ema_slow=Decimal("100"),
            atr_percent=Decimal("3"),
            relative_volume=Decimal("0.5"),
            spread_bps=Decimal("30"),
            event_risk=True,
        )
    )
    assert result.trend is TrendRegime.BEAR_TREND
    assert result.volatility is VolatilityRegime.HIGH_VOLATILITY
    assert result.liquidity is LiquidityRegime.LOW_LIQUIDITY
    assert result.event_risk is True
    assert result.strategy_entries_permitted is False


def test_weak_or_unaligned_trend_is_range_and_low_volatility_is_explicit() -> None:
    result = classify_regime(
        features(
            close=Decimal("101"),
            ema_fast=Decimal("100"),
            ema_slow=Decimal("102"),
            adx=Decimal("10"),
            atr_percent=Decimal("0.4"),
            relative_volume=Decimal("1"),
            spread_bps=Decimal("15"),
        )
    )
    assert result.trend is TrendRegime.RANGE
    assert result.volatility is VolatilityRegime.LOW_VOLATILITY
    assert result.liquidity is LiquidityRegime.NORMAL_LIQUIDITY


def test_regime_inputs_and_configuration_fail_closed() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        features(timestamp=datetime(2026, 9, 18, 10))
    with pytest.raises(ValueError, match="cannot be negative"):
        features(spread_bps=Decimal("-1"))
    with pytest.raises(ValueError, match="low ATR"):
        RegimeConfig(low_atr_percent=Decimal("2"), high_atr_percent=Decimal("1"))
