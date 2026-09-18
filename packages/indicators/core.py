"""Causal indicator implementations.

All returned series have the same length as their input and use ``None`` during
the documented warm-up.  Calculations only read values at or before an output
index. Inputs containing non-finite values are rejected instead of repaired.
"""

import math
from dataclasses import dataclass

type Number = int | float
type Series = tuple[float | None, ...]


@dataclass(frozen=True, slots=True)
class MACD:
    line: Series
    signal: Series
    histogram: Series


@dataclass(frozen=True, slots=True)
class BollingerBands:
    middle: Series
    upper: Series
    lower: Series


@dataclass(frozen=True, slots=True)
class Stochastic:
    k: Series
    d: Series


@dataclass(frozen=True, slots=True)
class Supertrend:
    value: Series
    direction: tuple[int | None, ...]


@dataclass(frozen=True, slots=True)
class Gap:
    index: int
    direction: str
    size: float
    previous_close: float
    current_open: float


def _values(values: list[Number] | tuple[Number, ...], name: str = "values") -> list[float]:
    result = [float(value) for value in values]
    if any(not math.isfinite(value) for value in result):
        raise ValueError(f"{name} must contain only finite values")
    return result


def _period(period: int) -> None:
    if period <= 0:
        raise ValueError("period must be positive")


def _same_length(*values: list[float]) -> None:
    if len({len(value) for value in values}) > 1:
        raise ValueError("input series must have equal lengths")


def sma(values: list[Number] | tuple[Number, ...], period: int) -> Series:
    """Simple moving average; warm-up is ``period - 1`` observations."""
    _period(period)
    source = _values(values)
    result: list[float | None] = [None] * len(source)
    rolling = 0.0
    for index, value in enumerate(source):
        rolling += value
        if index >= period:
            rolling -= source[index - period]
        if index >= period - 1:
            result[index] = rolling / period
    return tuple(result)


def ema(values: list[Number] | tuple[Number, ...], period: int) -> Series:
    """EMA seeded with an SMA; warm-up is ``period - 1`` observations."""
    _period(period)
    source = _values(values)
    result: list[float | None] = [None] * len(source)
    if len(source) < period:
        return tuple(result)
    current = sum(source[:period]) / period
    result[period - 1] = current
    alpha = 2.0 / (period + 1)
    for index in range(period, len(source)):
        current = alpha * source[index] + (1 - alpha) * current
        result[index] = current
    return tuple(result)


def rsi(values: list[Number] | tuple[Number, ...], period: int = 14) -> Series:
    """Wilder RSI; first value appears after ``period`` price changes."""
    _period(period)
    source = _values(values)
    result: list[float | None] = [None] * len(source)
    if len(source) <= period:
        return tuple(result)
    changes = [source[i] - source[i - 1] for i in range(1, len(source))]
    gain = sum(max(change, 0) for change in changes[:period]) / period
    loss = sum(max(-change, 0) for change in changes[:period]) / period

    def score() -> float:
        if loss == 0:
            return 100.0 if gain else 50.0
        return 100 - 100 / (1 + gain / loss)

    result[period] = score()
    for index in range(period + 1, len(source)):
        change = changes[index - 1]
        gain = (gain * (period - 1) + max(change, 0)) / period
        loss = (loss * (period - 1) + max(-change, 0)) / period
        result[index] = score()
    return tuple(result)


def macd(
    values: list[Number] | tuple[Number, ...], fast: int = 12, slow: int = 26, signal: int = 9
) -> MACD:
    if fast >= slow:
        raise ValueError("fast period must be smaller than slow period")
    fast_values, slow_values = ema(values, fast), ema(values, slow)
    line = tuple(
        None if left is None or right is None else left - right
        for left, right in zip(fast_values, slow_values, strict=True)
    )
    available = [value for value in line if value is not None]
    signal_tail = ema(available, signal)
    offset = len(line) - len(available)
    signal_line: Series = (None,) * offset + signal_tail
    histogram = tuple(
        None if left is None or right is None else left - right
        for left, right in zip(line, signal_line, strict=True)
    )
    return MACD(line, signal_line, histogram)


def _true_ranges(high: list[float], low: list[float], close: list[float]) -> list[float]:
    ranges = [high[0] - low[0]] if high else []
    ranges.extend(
        max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
        for i in range(1, len(high))
    )
    return ranges


def _wilder(values: list[float], period: int) -> Series:
    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return tuple(result)
    current = sum(values[:period]) / period
    result[period - 1] = current
    for index in range(period, len(values)):
        current = (current * (period - 1) + values[index]) / period
        result[index] = current
    return tuple(result)


def atr(
    high: list[Number] | tuple[Number, ...],
    low: list[Number] | tuple[Number, ...],
    close: list[Number] | tuple[Number, ...],
    period: int = 14,
) -> Series:
    _period(period)
    h, lo, c = _values(high, "high"), _values(low, "low"), _values(close, "close")
    _same_length(h, lo, c)
    if any(bottom > top for top, bottom in zip(h, lo, strict=True)):
        raise ValueError("high must be greater than or equal to low")
    return _wilder(_true_ranges(h, lo, c), period)


def adx(
    high: list[Number] | tuple[Number, ...],
    low: list[Number] | tuple[Number, ...],
    close: list[Number] | tuple[Number, ...],
    period: int = 14,
) -> Series:
    """Wilder ADX. The first ADX is available at index ``2*period-2``."""
    _period(period)
    h, lo, c = _values(high, "high"), _values(low, "low"), _values(close, "close")
    _same_length(h, lo, c)
    true_range = _wilder(_true_ranges(h, lo, c), period)
    plus = [0.0]
    minus = [0.0]
    for index in range(1, len(h)):
        up, down = h[index] - h[index - 1], lo[index - 1] - lo[index]
        plus.append(up if up > down and up > 0 else 0.0)
        minus.append(down if down > up and down > 0 else 0.0)
    plus_smoothed, minus_smoothed = _wilder(plus, period), _wilder(minus, period)
    dx: list[float] = []
    for index in range(period - 1, len(h)):
        tr = true_range[index]
        plus_value, minus_value = plus_smoothed[index], minus_smoothed[index]
        if tr is None or plus_value is None or minus_value is None:
            raise RuntimeError("internal ADX warm-up alignment failure")
        pdi = 100 * plus_value / tr if tr else 0.0
        mdi = 100 * minus_value / tr if tr else 0.0
        dx.append(100 * abs(pdi - mdi) / (pdi + mdi) if pdi + mdi else 0.0)
    tail = _wilder(dx, period)
    return (None,) * (period - 1) + tail


def bollinger_bands(
    values: list[Number] | tuple[Number, ...], period: int = 20, deviations: float = 2.0
) -> BollingerBands:
    _period(period)
    if deviations < 0 or not math.isfinite(deviations):
        raise ValueError("deviations must be finite and non-negative")
    source = _values(values)
    middle = sma(values, period)
    upper: list[float | None] = [None] * len(source)
    lower: list[float | None] = [None] * len(source)
    for index in range(period - 1, len(source)):
        window = source[index - period + 1 : index + 1]
        mean = middle[index]
        if mean is None:
            raise RuntimeError("internal Bollinger warm-up alignment failure")
        deviation = math.sqrt(sum((value - mean) ** 2 for value in window) / period)
        upper[index], lower[index] = mean + deviations * deviation, mean - deviations * deviation
    return BollingerBands(middle, tuple(upper), tuple(lower))


def vwap(
    high: list[Number] | tuple[Number, ...],
    low: list[Number] | tuple[Number, ...],
    close: list[Number] | tuple[Number, ...],
    volume: list[Number] | tuple[Number, ...],
) -> Series:
    h, lo, c, v = (_values(x) for x in (high, low, close, volume))
    _same_length(h, lo, c, v)
    if any(value < 0 for value in v):
        raise ValueError("volume cannot be negative")
    result: list[float | None] = []
    cumulative_price, cumulative_volume = 0.0, 0.0
    for top, bottom, last, quantity in zip(h, lo, c, v, strict=True):
        cumulative_price += ((top + bottom + last) / 3) * quantity
        cumulative_volume += quantity
        result.append(cumulative_price / cumulative_volume if cumulative_volume else None)
    return tuple(result)


def roc(values: list[Number] | tuple[Number, ...], period: int = 12) -> Series:
    _period(period)
    source = _values(values)
    result: list[float | None] = [None] * len(source)
    for index in range(period, len(source)):
        base = source[index - period]
        result[index] = 100 * (source[index] - base) / base if base else None
    return tuple(result)


def stochastic(
    high: list[Number] | tuple[Number, ...],
    low: list[Number] | tuple[Number, ...],
    close: list[Number] | tuple[Number, ...],
    period: int = 14,
    smooth: int = 3,
) -> Stochastic:
    _period(period)
    _period(smooth)
    h, lo, c = _values(high), _values(low), _values(close)
    _same_length(h, lo, c)
    k: list[float | None] = [None] * len(c)
    for index in range(period - 1, len(c)):
        top, bottom = (
            max(h[index - period + 1 : index + 1]),
            min(lo[index - period + 1 : index + 1]),
        )
        k[index] = 100 * (c[index] - bottom) / (top - bottom) if top != bottom else 50.0
    available = [value for value in k if value is not None]
    d = (None,) * (len(k) - len(available)) + sma(available, smooth)
    return Stochastic(tuple(k), d)


def relative_volume(volume: list[Number] | tuple[Number, ...], period: int = 20) -> Series:
    source = _values(volume, "volume")
    averages = sma(volume, period)
    result: list[float | None] = []
    for value, average in zip(source, averages, strict=True):
        result.append(None if average is None or average == 0 else value / average)
    return tuple(result)


def pivots(
    high: list[Number] | tuple[Number, ...],
    low: list[Number] | tuple[Number, ...],
    left: int = 2,
    right: int = 2,
) -> tuple[tuple[bool, ...], tuple[bool, ...]]:
    """Confirmed pivots, emitted at confirmation index to avoid repainting."""
    _period(left)
    _period(right)
    h, lo = _values(high), _values(low)
    _same_length(h, lo)
    highs, lows = [False] * len(h), [False] * len(h)
    for confirmed in range(left + right, len(h)):
        pivot = confirmed - right
        highs[confirmed] = h[pivot] == max(h[pivot - left : confirmed + 1])
        lows[confirmed] = lo[pivot] == min(lo[pivot - left : confirmed + 1])
    return tuple(highs), tuple(lows)


def support_resistance(
    high: list[Number] | tuple[Number, ...],
    low: list[Number] | tuple[Number, ...],
    left: int = 2,
    right: int = 2,
) -> tuple[Series, Series]:
    """Carry forward only confirmed pivot prices as resistance/support."""
    h, lo = _values(high), _values(low)
    pivot_high, pivot_low = pivots(high, low, left, right)
    resistance: list[float | None] = []
    support: list[float | None] = []
    current_high: float | None = None
    current_low: float | None = None
    for index in range(len(h)):
        if pivot_high[index]:
            current_high = h[index - right]
        if pivot_low[index]:
            current_low = lo[index - right]
        resistance.append(current_high)
        support.append(current_low)
    return tuple(resistance), tuple(support)


def gaps(
    open_: list[Number] | tuple[Number, ...],
    close: list[Number] | tuple[Number, ...],
    minimum_percent: float = 0.0,
) -> tuple[Gap, ...]:
    opening, closing = _values(open_, "open"), _values(close, "close")
    _same_length(opening, closing)
    if minimum_percent < 0:
        raise ValueError("minimum_percent cannot be negative")
    result: list[Gap] = []
    for index in range(1, len(opening)):
        previous = closing[index - 1]
        size = opening[index] - previous
        threshold = abs(previous) * minimum_percent / 100
        if abs(size) > threshold:
            result.append(
                Gap(index, "up" if size > 0 else "down", abs(size), previous, opening[index])
            )
    return tuple(result)


def supertrend(
    high: list[Number] | tuple[Number, ...],
    low: list[Number] | tuple[Number, ...],
    close: list[Number] | tuple[Number, ...],
    period: int = 10,
    multiplier: float = 3.0,
) -> Supertrend:
    if multiplier <= 0 or not math.isfinite(multiplier):
        raise ValueError("multiplier must be finite and positive")
    h, lo, c = _values(high), _values(low), _values(close)
    _same_length(h, lo, c)
    ranges = atr(high, low, close, period)
    values: list[float | None] = [None] * len(c)
    directions: list[int | None] = [None] * len(c)
    upper, lower = 0.0, 0.0
    direction = 1
    for index in range(period - 1, len(c)):
        current_atr = ranges[index]
        if current_atr is None:
            raise RuntimeError("internal Supertrend warm-up alignment failure")
        midpoint = (h[index] + lo[index]) / 2
        basic_upper, basic_lower = (
            midpoint + multiplier * current_atr,
            midpoint - multiplier * current_atr,
        )
        if index == period - 1:
            upper, lower = basic_upper, basic_lower
        else:
            upper = basic_upper if basic_upper < upper or c[index - 1] > upper else upper
            lower = basic_lower if basic_lower > lower or c[index - 1] < lower else lower
            if direction == -1 and c[index] > upper:
                direction = 1
            elif direction == 1 and c[index] < lower:
                direction = -1
        directions[index] = direction
        values[index] = lower if direction == 1 else upper
    return Supertrend(tuple(values), tuple(directions))
