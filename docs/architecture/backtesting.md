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

The cost boundary is pluggable. The India model consumes an effective-dated schedule and itemizes brokerage,
exchange, SEBI, IPFT, GST, side-specific STT, and buy-side stamp duty. No unverified “current” statutory schedule
is embedded; runs must provide an owner-verified schedule for their product and historical effective date.

Outputs include an immutable trade ledger, rejected decisions, equity/drawdown curves, net profit, return, win
rate, average win/loss, expectancy, profit factor, maximum drawdown, Sharpe ratio, turnover, and consecutive
wins/losses. These metrics do not label a strategy successful.

The reporting layer derives Asia/Kolkata daily and monthly returns, downside-only Sortino, linear annualized
return-to-drawdown Calmar, elapsed-time exposure, and long/short performance from the immutable result. The
Calmar numerator is explicitly a linear annualization of observed return, not a CAGR, and reports never assign a
success label.

## Robustness validation

Chronological splitting never shuffles and requires non-empty train, validation, and held-out test partitions.
Walk-forward folds place validation strictly after training and test strictly after validation, supporting either
expanding or rolling training windows. Parameter stability reports sign consistency and the largest normalized
neighbor-to-neighbor score change so an isolated optimum is rejected rather than celebrated.

Monte Carlo analysis deterministically shuffles observed net trade P&Ls with a recorded seed and reports final
equity percentiles, sequence drawdown, and loss probability. It measures ordering risk only and does not invent
unseen market regimes. Cost sensitivity applies additional basis-point costs to two-sided turnover. Benchmark
comparison requires equal-length aligned equity series and reports strategy, benchmark, and excess return.
The out-of-sample orchestrator scores every configured candidate using only the train and validation partitions,
selects deterministically by validation score, then invokes the held-out test evaluator exactly once for the
selected candidate. Candidate scores must be finite and the immutable result retains the full selection audit.

## Current limitations

Partial fills, limit/stop-limit orders, owner-verified India statutory schedules, margin, holidays/expiry,
regime/instrument reports, CAGR-based annualization, and multi-dimensional parameter-search orchestration remain
Phase 5 work.
