# Deterministic market regimes — version 1

The regime classifier consumes one timestamped feature snapshot rather than a raw series, so it cannot inspect
future observations. Inputs must be timezone-aware; prices/EMAs must be positive and ADX, ATR percentage,
relative volume, and spread must be non-negative. Output has independent trend, volatility, liquidity, and
event-risk axes, bounded confidence, supporting features, timestamp, and rule version.

## Trend

- Bull trend: `ADX >= 20` and `close > fast EMA > slow EMA`.
- Bear trend: `ADX >= 20` and `close < fast EMA < slow EMA`.
- Otherwise: range.

Thresholds are configurable. Confidence uses bounded ADX strength and EMA separation; it is an explanatory
score, not a calibrated probability.

## Volatility

ATR is expressed as a percentage of price before classification. `ATR% >= 2` is high volatility, `ATR% <= 0.5`
is low volatility, and values between those thresholds are normal volatility. Thresholds cannot overlap.

## Liquidity

High liquidity requires both `relative volume >= 1.2` and `spread <= 10 bps`. Low liquidity requires either
`relative volume <= 0.7` or `spread >= 25 bps`; remaining snapshots are normal liquidity. This deliberately does
not infer liquidity from last-traded price alone.

## Event risk

Event risk is supplied by a future point-in-time event-calendar service and remains an independent Boolean axis.
When true, `strategy_entries_permitted` is false. The classifier does not erase other regime labels and cannot
place or authorize an order.
