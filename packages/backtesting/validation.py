"""Leakage-resistant backtest validation and robustness analysis."""

from dataclasses import dataclass
from decimal import Decimal
from itertools import pairwise
from statistics import median

from packages.backtesting.engine import BacktestTrade


@dataclass(frozen=True, slots=True)
class ChronologicalSplit[T]:
    train: tuple[T, ...]
    validation: tuple[T, ...]
    test: tuple[T, ...]


@dataclass(frozen=True, slots=True)
class WalkForwardFold[T]:
    train: tuple[T, ...]
    validation: tuple[T, ...]
    test: tuple[T, ...]


@dataclass(frozen=True, slots=True)
class MonteCarloResult:
    seed: int
    simulations: int
    median_final_equity: Decimal
    fifth_percentile_final_equity: Decimal
    ninety_fifth_percentile_final_equity: Decimal
    median_maximum_drawdown: Decimal
    worst_maximum_drawdown: Decimal
    probability_of_loss: Decimal


@dataclass(frozen=True, slots=True)
class ParameterStabilityResult:
    median_score: Decimal
    minimum_score: Decimal
    maximum_score: Decimal
    positive_fraction: Decimal
    maximum_neighbor_change: Decimal
    stable: bool


@dataclass(frozen=True, slots=True)
class CostSensitivityPoint:
    additional_cost_bps: Decimal
    adjusted_net_profit: Decimal
    profitable: bool


@dataclass(frozen=True, slots=True)
class BenchmarkComparison:
    strategy_return: Decimal
    benchmark_return: Decimal
    excess_return: Decimal


def chronological_split[T](
    values: tuple[T, ...],
    *,
    train_fraction: Decimal = Decimal("0.6"),
    validation_fraction: Decimal = Decimal("0.2"),
) -> ChronologicalSplit[T]:
    """Split without shuffling; every train item precedes validation and test."""
    if not values:
        raise ValueError("chronological split requires observations")
    if train_fraction <= 0 or validation_fraction <= 0:
        raise ValueError("train and validation fractions must be positive")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("train plus validation fraction must be below 1")
    train_end = int(Decimal(len(values)) * train_fraction)
    validation_end = train_end + int(Decimal(len(values)) * validation_fraction)
    if train_end < 1 or validation_end <= train_end or validation_end >= len(values):
        raise ValueError("split produces an empty partition")
    return ChronologicalSplit(
        values[:train_end], values[train_end:validation_end], values[validation_end:]
    )


def walk_forward_folds[T](
    values: tuple[T, ...],
    *,
    train_size: int,
    validation_size: int,
    test_size: int,
    step_size: int | None = None,
    expanding: bool = True,
) -> tuple[WalkForwardFold[T], ...]:
    """Build ordered folds with validation strictly between train and test."""
    if min(train_size, validation_size, test_size) <= 0:
        raise ValueError("walk-forward window sizes must be positive")
    step = step_size or test_size
    if step <= 0:
        raise ValueError("walk-forward step must be positive")
    folds: list[WalkForwardFold[T]] = []
    offset = 0
    while True:
        train_start = 0 if expanding else offset
        train_end = offset + train_size
        validation_end = train_end + validation_size
        test_end = validation_end + test_size
        if test_end > len(values):
            break
        folds.append(
            WalkForwardFold(
                values[train_start:train_end],
                values[train_end:validation_end],
                values[validation_end:test_end],
            )
        )
        offset += step
    if not folds:
        raise ValueError("insufficient observations for one walk-forward fold")
    return tuple(folds)


def _maximum_drawdown(path: list[Decimal]) -> Decimal:
    peak = path[0]
    maximum = Decimal(0)
    for equity in path:
        peak = max(peak, equity)
        if peak > 0:
            maximum = max(maximum, (peak - equity) / peak)
    return maximum


def _percentile(sorted_values: list[Decimal], percentile: Decimal) -> Decimal:
    if not sorted_values:
        raise ValueError("percentile requires values")
    index = int(
        (Decimal(len(sorted_values) - 1) * percentile).to_integral_value(rounding="ROUND_HALF_UP")
    )
    return sorted_values[index]


def _deterministic_shuffle(values: list[Decimal], state: int) -> tuple[list[Decimal], int]:
    """Fisher-Yates using a fixed LCG; reproducibility only, never security."""
    result = values.copy()
    for index in range(len(result) - 1, 0, -1):
        state = (1664525 * state + 1013904223) % (2**32)
        selected = state % (index + 1)
        result[index], result[selected] = result[selected], result[index]
    return result, state


def monte_carlo_trade_sequences(
    net_pnls: tuple[Decimal, ...],
    *,
    initial_capital: Decimal,
    simulations: int = 1000,
    seed: int = 7,
) -> MonteCarloResult:
    """Shuffle observed trade P&Ls; this measures sequence risk, not unseen-market risk."""
    if not net_pnls:
        raise ValueError("Monte Carlo requires trades")
    if initial_capital <= 0 or simulations <= 0:
        raise ValueError("capital and simulation count must be positive")
    state = seed % (2**32)
    finals: list[Decimal] = []
    drawdowns: list[Decimal] = []
    losing = 0
    source = list(net_pnls)
    for _ in range(simulations):
        shuffled, state = _deterministic_shuffle(source, state)
        path = [initial_capital]
        for pnl in shuffled:
            path.append(path[-1] + pnl)
        finals.append(path[-1])
        drawdowns.append(_maximum_drawdown(path))
        losing += path[-1] < initial_capital
    finals.sort()
    drawdowns.sort()
    return MonteCarloResult(
        seed,
        simulations,
        Decimal(median(finals)),
        _percentile(finals, Decimal("0.05")),
        _percentile(finals, Decimal("0.95")),
        Decimal(median(drawdowns)),
        drawdowns[-1],
        Decimal(losing) / simulations,
    )


def assess_parameter_stability(
    ordered_scores: tuple[Decimal, ...],
    *,
    minimum_positive_fraction: Decimal = Decimal("0.6"),
    maximum_neighbor_change: Decimal = Decimal("0.5"),
) -> ParameterStabilityResult:
    """Reject isolated optima by checking neighboring score continuity and sign."""
    if len(ordered_scores) < 3:
        raise ValueError("parameter stability requires at least three ordered scores")
    if not Decimal(0) <= minimum_positive_fraction <= Decimal(1):
        raise ValueError("minimum positive fraction must be between 0 and 1")
    if maximum_neighbor_change < 0:
        raise ValueError("maximum neighbor change cannot be negative")
    changes = [
        abs(right - left) / max(abs(left), abs(right), Decimal("0.0000001"))
        for left, right in pairwise(ordered_scores)
    ]
    positive_fraction = Decimal(sum(score > 0 for score in ordered_scores)) / len(ordered_scores)
    observed_change = max(changes)
    return ParameterStabilityResult(
        Decimal(median(ordered_scores)),
        min(ordered_scores),
        max(ordered_scores),
        positive_fraction,
        observed_change,
        positive_fraction >= minimum_positive_fraction
        and observed_change <= maximum_neighbor_change,
    )


def cost_sensitivity(
    trades: tuple[BacktestTrade, ...], extra_costs_bps: tuple[Decimal, ...]
) -> tuple[CostSensitivityPoint, ...]:
    if any(cost < 0 for cost in extra_costs_bps):
        raise ValueError("additional costs cannot be negative")
    base = sum((trade.net_pnl for trade in trades), Decimal(0))
    turnover = sum(
        ((trade.entry_price + trade.exit_price) * trade.quantity for trade in trades), Decimal(0)
    )
    return tuple(
        CostSensitivityPoint(
            cost, base - turnover * cost / 10000, base - turnover * cost / 10000 > 0
        )
        for cost in extra_costs_bps
    )


def compare_benchmark(
    strategy_equity: tuple[Decimal, ...], benchmark_equity: tuple[Decimal, ...]
) -> BenchmarkComparison:
    if len(strategy_equity) < 2 or len(strategy_equity) != len(benchmark_equity):
        raise ValueError(
            "strategy and benchmark require equal aligned series of length at least two"
        )
    if strategy_equity[0] <= 0 or benchmark_equity[0] <= 0:
        raise ValueError("initial equity values must be positive")
    strategy_return = strategy_equity[-1] / strategy_equity[0] - 1
    benchmark_return = benchmark_equity[-1] / benchmark_equity[0] - 1
    return BenchmarkComparison(
        strategy_return, benchmark_return, strategy_return - benchmark_return
    )
