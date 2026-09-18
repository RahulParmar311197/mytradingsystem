import math

import pytest

from packages.indicators import (
    adx,
    atr,
    bollinger_bands,
    ema,
    gaps,
    macd,
    pivots,
    relative_volume,
    roc,
    rsi,
    sma,
    stochastic,
    supertrend,
    support_resistance,
    vwap,
)


def test_moving_averages_have_explicit_warmup_and_reference_values() -> None:
    values = [1, 2, 3, 4, 5]
    assert sma(values, 3) == (None, None, 2.0, 3.0, 4.0)
    assert ema(values, 3) == (None, None, 2.0, 3.0, 4.0)
    assert rsi([1, 2, 3, 2, 4], 3) == (None, None, None, 66.66666666666666, 83.33333333333333)


def test_volatility_momentum_and_volume_indicators() -> None:
    high, low, close = [11, 12, 13, 14, 15], [9, 10, 11, 12, 13], [10, 11, 12, 13, 14]
    assert atr(high, low, close, 3) == (None, None, 2.0, 2.0, 2.0)
    assert adx(high, low, close, 2) == (None, None, 100.0, 100.0, 100.0)
    assert roc(close, 2) == (None, None, 20.0, pytest.approx(18.181818), pytest.approx(16.666667))
    assert vwap(high[:2], low[:2], close[:2], [10, 30]) == (10.0, 10.75)
    assert relative_volume([10, 20, 30], 2) == (None, pytest.approx(4 / 3), 1.2)


def test_composite_indicators_are_aligned_and_causal() -> None:
    values = list(range(1, 40))
    result = macd(values, fast=3, slow=5, signal=2)
    assert result.line[:4] == (None, None, None, None)
    assert result.signal[:5] == (None, None, None, None, None)
    assert result.histogram[-1] == pytest.approx(0)
    bands = bollinger_bands([1, 2, 3], 3, 2)
    assert bands.middle == (None, None, 2.0)
    assert bands.upper[-1] == pytest.approx(2 + 2 * math.sqrt(2 / 3))
    oscillator = stochastic([3, 4, 5, 6], [1, 2, 3, 4], [2, 3, 4, 5], 3, 2)
    assert oscillator.k == (None, None, 75.0, 75.0)
    assert oscillator.d == (None, None, None, 75.0)


def test_confirmed_structure_does_not_repaint_or_look_ahead() -> None:
    high, low = [1, 3, 2, 4, 2], [0, 1, 0, 2, 1]
    pivot_high, pivot_low = pivots(high, low, 1, 1)
    assert pivot_high == (False, False, True, False, True)
    assert pivot_low == (False, False, False, True, False)
    resistance, support = support_resistance(high, low, 1, 1)
    assert resistance == (None, None, 3.0, 3.0, 4.0)
    assert support == (None, None, None, 0.0, 0.0)
    found = gaps([10, 12, 10], [10, 11, 9], minimum_percent=5)
    assert [(gap.index, gap.direction, gap.size) for gap in found] == [
        (1, "up", 2.0),
        (2, "down", 1.0),
    ]


def test_supertrend_warms_up_and_rejects_bad_inputs() -> None:
    result = supertrend([11, 12, 13, 14], [9, 10, 11, 12], [10, 11, 12, 13], 3, 2)
    assert result.value[:2] == (None, None)
    assert result.direction == (None, None, 1, 1)
    with pytest.raises(ValueError, match="finite"):
        sma([1, float("nan")], 2)
    with pytest.raises(ValueError, match="equal lengths"):
        atr([2], [1, 2], [1], 2)
