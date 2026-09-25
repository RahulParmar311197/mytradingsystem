# Technical indicator definitions

All indicators are deterministic and causal: the value at index `i` uses observations `0..i` only. Series are
index-aligned and contain `None` until sufficient data exists. Non-finite values and mismatched OHLCV lengths
are rejected rather than repaired. Comparisons to external libraries must use a `1e-9` absolute tolerance and
the seeding rules below; differing seed conventions can legitimately produce different early values.

- **SMA(n):** arithmetic mean of the last `n` values; warm-up `n-1`.
- **EMA(n):** multiplier `2/(n+1)`, seeded by the first `n`-value SMA; warm-up `n-1`.
- **RSI(n):** Wilder-smoothed gains and losses, seeded from `n` changes; warm-up `n`.
- **MACD:** fast EMA minus slow EMA; signal is an EMA of available MACD values; histogram is their difference.
- **ATR(n):** Wilder mean of true range `max(H-L, |H-Cprev|, |L-Cprev|)`; warm-up `n-1`.
- **ADX(n):** Wilder-smoothed directional movement and true range, followed by Wilder smoothing of DX; warm-up
  `2n-2`.
- **Bollinger Bands:** population standard deviation around SMA, with configurable non-negative multiplier.
- **VWAP:** cumulative typical price `(H+L+C)/3`, weighted by non-negative volume.
- **Supertrend:** midpoint plus/minus configured ATR multiple, with trailing bands and close-based direction
  changes.
- **ROC(n):** percentage change from `i-n`; a zero denominator produces `None`.
- **Stochastic:** `%K = 100(C-lowest)/(highest-lowest)` over `n`; `%D` is an SMA of available `%K` values.
- **Volume SMA / relative volume:** ordinary SMA and volume divided by its SMA.
- **Pivots:** a candidate equal to the window extreme is published at `candidate + right`; it never appears at
  the historical candidate index. Support/resistance carries the latest confirmed pivot price forward.
- **Gap:** current open differs from the previous close by more than the configured percentage threshold.

Indicator outputs are analytical floats. Executable prices and accounting amounts remain `Decimal` and must
be rounded to the instrument tick size at an execution boundary.
