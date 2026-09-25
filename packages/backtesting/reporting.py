"""Deterministic performance reporting derived from a completed backtest."""

from dataclasses import dataclass
from decimal import Decimal
from math import sqrt
from zoneinfo import ZoneInfo

from packages.backtesting.engine import BacktestResult
from packages.domain.models import SignalAction


@dataclass(frozen=True, slots=True)
class PeriodReturn:
    period: str
    return_fraction: Decimal


@dataclass(frozen=True, slots=True)
class DirectionPerformance:
    direction: SignalAction
    trade_count: int
    net_profit: Decimal
    win_rate: Decimal


@dataclass(frozen=True, slots=True)
class PerformanceReport:
    daily_returns: tuple[PeriodReturn, ...]
    monthly_returns: tuple[PeriodReturn, ...]
    sortino_ratio: Decimal | None
    calmar_ratio: Decimal | None
    exposure_fraction: Decimal
    by_direction: tuple[DirectionPerformance, ...]


def _period_returns(
    result: BacktestResult, timezone: ZoneInfo, *, monthly: bool
) -> tuple[PeriodReturn, ...]:
    closes: dict[str, Decimal] = {}
    for timestamp, equity in result.equity_curve:
        local = timestamp.astimezone(timezone)
        key = f"{local.year:04d}-{local.month:02d}" if monthly else local.date().isoformat()
        closes[key] = equity
    previous = result.initial_capital
    returns: list[PeriodReturn] = []
    for period, close in closes.items():
        value = close / previous - 1 if previous else Decimal(0)
        returns.append(PeriodReturn(period, value))
        previous = close
    return tuple(returns)


def _sortino(result: BacktestResult, annualization_periods: int) -> Decimal | None:
    returns = [
        result.equity_curve[index][1] / result.equity_curve[index - 1][1] - 1
        for index in range(1, len(result.equity_curve))
        if result.equity_curve[index - 1][1] != 0
    ]
    if len(returns) < 2:
        return None
    downside = [min(value, Decimal(0)) for value in returns]
    downside_variance = sum((value * value for value in downside), Decimal(0)) / len(downside)
    if downside_variance == 0:
        return None
    mean = sum(returns, Decimal(0)) / len(returns)
    return (
        mean
        / Decimal(str(sqrt(float(downside_variance))))
        * Decimal(str(sqrt(annualization_periods)))
    )


def _direction_performance(result: BacktestResult) -> tuple[DirectionPerformance, ...]:
    output: list[DirectionPerformance] = []
    for direction in (SignalAction.LONG, SignalAction.SHORT):
        trades = tuple(trade for trade in result.trades if trade.direction is direction)
        if not trades:
            continue
        wins = sum(trade.net_pnl > 0 for trade in trades)
        output.append(
            DirectionPerformance(
                direction,
                len(trades),
                sum((trade.net_pnl for trade in trades), Decimal(0)),
                Decimal(wins) / len(trades),
            )
        )
    return tuple(output)


def build_performance_report(
    result: BacktestResult,
    *,
    presentation_timezone: str = "Asia/Kolkata",
    annualization_periods: int = 252,
) -> PerformanceReport:
    """Build an immutable report without changing or relabelling the backtest result."""
    if annualization_periods <= 0:
        raise ValueError("annualization periods must be positive")
    timezone = ZoneInfo(presentation_timezone)
    exposure = Decimal(0)
    if len(result.equity_curve) > 1:
        elapsed = result.equity_curve[-1][0] - result.equity_curve[0][0]
        occupied_seconds = sum(
            ((trade.exited_at - trade.entered_at).total_seconds() for trade in result.trades), 0.0
        )
        if elapsed.total_seconds() > 0:
            exposure = min(Decimal(1), Decimal(str(occupied_seconds / elapsed.total_seconds())))
    calmar = None
    if result.metrics.maximum_drawdown > 0 and len(result.equity_curve) > 1:
        periods = len(result.equity_curve) - 1
        annualized_return = result.metrics.total_return * Decimal(annualization_periods) / periods
        calmar = annualized_return / result.metrics.maximum_drawdown
    return PerformanceReport(
        _period_returns(result, timezone, monthly=False),
        _period_returns(result, timezone, monthly=True),
        _sortino(result, annualization_periods),
        calmar,
        exposure,
        _direction_performance(result),
    )
