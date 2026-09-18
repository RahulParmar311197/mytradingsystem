# Event-driven backtesting

The first Phase 5 slice consumes closed chronological candles and the same non-executable `DecisionResult`
contract used by the decision layer. At each candle close the provider receives only the prefix ending at that
candle. An entry or exit decision is queued and cannot execute before the next candle open. A final-candle
decision is never filled because no later market event exists.

Market fills apply configurable adverse slippage. Stops and targets are evaluated only after entry; if both are
inside one candle, the stop wins to avoid optimistic intrabar ordering. Gap-through stops receive the adverse
open, while favorable target gaps receive the open. Entry geometry is revalidated against the actual next-open
fill, so a gap that moves through the stop or target is rejected rather than creating nonsensical risk.

The default backtest-only policy sizes from equity, requested risk fraction, and actual fill-to-stop distance,
capped by notional exposure. It implements the `BacktestRiskPolicy` protocol and records rejections, but is not
the Phase 7 independent production risk engine. Variable basis-point charges and flat per-order charges apply on
both entry and exit. Entry cost is reflected immediately in marked equity.

Outputs include an immutable trade ledger, rejected decisions, equity/drawdown curves, net profit, return, win
rate, average win/loss, expectancy, profit factor, maximum drawdown, Sharpe ratio, turnover, and consecutive
wins/losses. These metrics do not label a strategy successful.

## Robustness validation

Chronological splitting never shuffles and requires non-empty train, validation, and held-out test partitions.
Walk-forward folds place validation strictly after training and test strictly after validation, supporting either
expanding or rolling training windows. Parameter stability reports sign consistency and the largest normalized
neighbor-to-neighbor score change so an isolated optimum is rejected rather than celebrated.

Monte Carlo analysis deterministically shuffles observed net trade P&Ls with a recorded seed and reports final
equity percentiles, sequence drawdown, and loss probability. It measures ordering risk only and does not invent
unseen market regimes. Cost sensitivity applies additional basis-point costs to two-sided turnover. Benchmark
comparison requires equal-length aligned equity series and reports strategy, benchmark, and excess return.

## Current limitations

Partial fills, limit/stop-limit orders, India-specific statutory charge schedules, margin, holidays/expiry,
daily/monthly and regime/instrument/direction reports, Sortino/Calmar, exposure duration, parameter search
orchestration, and full out-of-sample strategy reruns remain Phase 5 work.
