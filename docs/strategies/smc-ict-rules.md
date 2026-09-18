# Deterministic SMC/ICT rules — version 1

SMC and ICT terminology is subjective unless reduced to executable rules. The engine labels only the concepts
defined below and does **not** claim to detect institutional activity or trader intent. It accepts one strictly
chronological instrument/timeframe series containing closed candles only.

Candle timestamps are interval starts. Every `detected_at`, `confirmed_at`, `available_at`, and analysis `as_of`
time is therefore `candle.timestamp + timeframe_seconds`; evidence retains original interval-start timestamps.
This prevents a label from appearing at the start of the candle that is required to confirm it.

## Confirmed swing

For configured positive integers `L` and `R`, candle `i` is a swing high when its high is strictly greater than
every other high in `[i-L, i+R]`. A swing low uses the symmetric strict-low rule. The event is unavailable until
candle `i+R` closes and is emitted with that confirmation time, the full window of evidence timestamps, an
objective magnitude-based confidence, and its close-through invalidation condition. Equal extrema do not
produce a swing; equal-level liquidity is instead derived from two separately confirmed strict swings.

Internal and external structure use the same strict, non-repainting swing equation but independent positive
`left/right` windows. Internal defaults to `1/1`; external defaults to `2/2`. Every swing and structure event is
tagged with its scope. BOS, CHOCH, and MSS state is tracked independently per scope, preventing a small internal
break from silently changing external trend. Order-block origin selection deliberately consumes external
structure only; an internal break cannot create an execution-facing block label.

## Break of Structure and Change of Character

Only a swing confirmed before the breakout candle may be used. A bullish break requires a close strictly above
the latest confirmed swing high; a bearish break requires a close strictly below the latest confirmed swing
low. Each swing can be broken only once. A break agreeing with the current structural direction, or the first
observed break, is BOS. A break opposing the current structural direction is CHOCH. A wick alone is never a
break. The broken swing, its confirmation candle, and breakout candle are recorded as evidence.

An MSS is emitted in addition to CHOCH only when the CHOCH candle is also a qualifying displacement candle in
the new direction. Its evidence is the union of the swing evidence and displacement lookback. Thus every MSS
has an underlying CHOCH, but a CHOCH without same-candle displacement is not an MSS.

## Displacement

Let `B` be the absolute real body and `A` the arithmetic mean of absolute real bodies over the configured `N`
immediately preceding closed candles. A candle is eligible when `A > 0` and `B >= A * body_multiple`. Its close
location is `(close-low)/(high-low)`. A bullish displacement additionally requires `close > open` and close
location at or above the configured threshold. A bearish displacement requires `close < open` and close
location at or below `1-threshold`. Zero-range candles cannot qualify. Detection occurs at that candle's close.

## Equal highs, equal lows, and liquidity side

Only consecutive confirmed swings of the same type are compared. Their absolute price difference must be no
greater than `midpoint * tolerance_percent / 100`. Two swing highs form a buy-side-liquidity band and two swing
lows form a sell-side-liquidity band. The band becomes available when the second swing is confirmed, not at its
historical pivot candle. Its bounds preserve the two actual prices rather than silently averaging them.

## Reference levels

Calendar grouping is performed in `Asia/Kolkata`. Previous-day levels use the most recent earlier local trading
date present in the snapshot; previous-week levels use the most recent earlier ISO week. Their high/low levels
become available at the final source candle's close. Current-session high/low uses only the current local date's
closed candles through `as_of`, so it can evolve during the session without reading later candles.

## Premium, discount, and OTE

The dealing range uses the latest confirmed swing high `H` and latest confirmed swing low `L`, provided `H>L`,
and becomes available at the later confirmation time. Discount is `[L, L+0.5(H-L)]`; premium is
`[L+0.5(H-L), H]`. Bullish OTE is `[L+0.62(H-L), L+0.79(H-L)]`. Bearish OTE is
`[H-0.79(H-L), H-0.62(H-L)]`. These are geometric zones, not trade recommendations.

## Kill zones

Kill zones are named half-open local-time intervals (`start <= time < end`) and support overnight windows.
Defaults are fixed IST windows: Asia 05:30–09:30, NSE open 09:15–10:15, London-labelled 12:30–15:30, and
New-York-labelled 18:30–21:30. The latter labels deliberately say `fixed_ist`: they do not auto-adjust for UK or
US daylight saving time. Strategies requiring DST-aware foreign sessions must supply different zone rules.

## Order, mitigation, and breaker blocks

Blocks are created only for a structural-break candle that also qualifies as displacement in the same direction.
Within the configured finite lookback, a bullish block uses the most recent bearish candle and a bearish block
uses the most recent bullish candle. The zone is that origin candle's full `[low, high]`; if no opposing candle
exists, no block is invented. It becomes available at the displacement-confirmed break close and retains the
origin, swing-break, and displacement evidence.

A first later closed candle whose range overlaps the zone emits a mitigation-block event and marks the source
order block mitigated. A bullish source block is invalidated only by a later close below its low; a bearish
source block only by a later close above its high. That close-through emits a breaker block over the same bounds
in the opposite direction. Merely wicking through a boundary does not create a breaker. Lifecycle evaluation
uses only candles after block detection, and the first mitigation/invalidation times are retained.

## Liquidity sweep

A bearish-side swing high is swept when a later candle's high exceeds `level + tolerance` while its close is at
or below the level. A bullish-side swing low is swept when a later low is below `level - tolerance` while its
close is at or above the level. `tolerance = level * configured_percent / 100`. The resulting direction is the
rejection direction: bearish after taking a high, bullish after taking a low. This rule describes price action,
not the identity or motivation of market participants.

## Fair value gap

For closed candles `A, B, C`, a bullish FVG exists when `C.low > A.high`; its interval is `[A.high, C.low]`.
A bearish FVG exists when `C.high < A.low`; its interval is `[C.high, A.low]`. The gap must satisfy
`100 * width / midpoint >= minimum_gap_percent`. It becomes available only when `C` closes. The three candle
timestamps are retained as evidence. A bullish gap's stated invalidation is a later trade at or below its lower
bound; a bearish gap's is a later trade at or above its upper bound. Consequent encroachment is the exact
arithmetic midpoint `(lower + upper) / 2`.

Gap lifecycle is evaluated only with candles after the detection candle. A bullish gap becomes mitigated when a
later low is strictly below its upper bound and invalidated when a later low is at or below its lower bound. A
bearish gap uses the symmetric high tests. The first mitigation and invalidation timestamps are retained. A
wick can invalidate the source FVG, but an inverse FVG is created only on a close through the far boundary: a
close below the lower bound turns a bullish FVG into a bearish IFVG, while a close above the upper bound turns a
bearish FVG into a bullish IFVG. This distinction prevents wick rejection from being mislabeled as inversion.

## Confidence and overlays

Pattern confidence is a bounded display score: `min(1, 0.5 + magnitude/reference_price)`. It is not a calibrated
probability and cannot authorize an order. Every result includes the rule version, timestamps, evidence,
invalidation text, and human-readable explanation. Overlay records contain start/end time, price bounds, label,
and color without depending on a specific chart library.

## Implementation boundary

The deterministic backend definitions requested for Phase 3 now have executable rules and fixtures. Overlay
records are chart-library-neutral contracts; actual browser rendering remains frontend work and must not be
represented as complete until it is visually and end-to-end tested.
