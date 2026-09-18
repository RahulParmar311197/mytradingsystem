# Initial deterministic strategies

All strategies consume one immutable point-in-time context and return either `LONG`, `SHORT`, or the common
`NO_TRADE` outcome. They return proposed entry, stop, target, and a maximum-risk-fraction **request** only. They
cannot create an order and the independent risk engine may reject or resize every future intent. Common entry
locks are outside-session, event risk, low liquidity, and unsupported regime.

## Trend continuation 1.0.0

Requires aligned current and higher-timeframe bull/bear regime, close on the directional side of both fast EMA
and VWAP, and relative volume at least 1.2. Uses 1 ATR stop and a 2R target by default.

## Liquidity-sweep reversal 1.0.0

Requires a deterministic liquidity-sweep direction and matching market-structure confirmation. It supports
trend and range regimes because confirmation, rather than a presumed reversal, is mandatory.

## Opening-range breakout 1.0.0

Requires a completed opening range, a close strictly outside its bounds, and relative volume at least 1.2. A
retest can be made mandatory through versioned configuration. No signal exists while the range is incomplete.

## FVG continuation 1.0.0

Requires an active FVG with complete bounds, current and higher-timeframe trend matching its direction, and the
current close inside the zone. It does not treat historical or invalidated FVG existence as sufficient.

## Range mean reversion 1.0.0

Runs only in the range regime. A z-score at or below -2 requests a long; at or above +2 requests a short. The
target is VWAP and the default stop is 1 ATR. Trend regimes produce `NO_TRADE` rather than forcing a fade.

Defaults request at most 0.5% account risk and configuration rejects requests above 2%. This is not position
sizing: quantity is intentionally absent until the independent risk engine evaluates account and portfolio state.
