from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from packages.backtesting import (
    BacktestTrade,
    ExitReason,
    assess_parameter_stability,
    chronological_split,
    compare_benchmark,
    cost_sensitivity,
    monte_carlo_trade_sequences,
    run_out_of_sample_selection,
    walk_forward_folds,
)
from packages.domain.models import SignalAction


def test_out_of_sample_selection_never_exposes_test_to_parameter_scoring() -> None:
    split = chronological_split(tuple(range(10)))
    scoring_observations: list[tuple[tuple[int, ...], tuple[int, ...]]] = []
    tested: list[tuple[str, tuple[int, ...]]] = []

    def score(candidate: str, train: tuple[int, ...], validation: tuple[int, ...]) -> Decimal:
        scoring_observations.append((train, validation))
        return {"conservative": Decimal("0.4"), "selected": Decimal("0.8")}[candidate]

    def test(candidate: str, observations: tuple[int, ...]) -> str:
        tested.append((candidate, observations))
        return "held-out-result"

    result = run_out_of_sample_selection(split, ("conservative", "selected"), score, test)
    assert result.selected_candidate == "selected"
    assert result.test_result == "held-out-result"
    assert scoring_observations == [(split.train, split.validation)] * 2
    assert tested == [("selected", split.test)]


def test_out_of_sample_selection_has_deterministic_ties_and_rejects_nonfinite() -> None:
    split = chronological_split(tuple(range(10)))
    tied = run_out_of_sample_selection(
        split,
        ("first", "second"),
        lambda candidate, train, validation: Decimal(1),
        lambda candidate, test: candidate,
    )
    assert tied.selected_candidate == "first"
    with pytest.raises(ValueError, match="finite"):
        run_out_of_sample_selection(
            split,
            ("invalid",),
            lambda candidate, train, validation: Decimal("NaN"),
            lambda candidate, test: candidate,
        )


def test_out_of_sample_selection_rejects_empty_inputs() -> None:
    split = chronological_split(tuple(range(10)))
    with pytest.raises(ValueError, match="candidates"):
        run_out_of_sample_selection(split, (), lambda candidate, train, validation: Decimal(1), str)


def trade(net: str, entry: str = "100", exit_: str = "102") -> BacktestTrade:
    now = datetime(2026, 9, 18, tzinfo=UTC)
    net_pnl = Decimal(net)
    return BacktestTrade(
        SignalAction.LONG,
        Decimal("10"),
        now,
        now,
        now,
        Decimal(entry),
        Decimal(exit_),
        Decimal("98"),
        Decimal("104"),
        net_pnl,
        Decimal(0),
        net_pnl,
        ExitReason.TARGET if net_pnl > 0 else ExitReason.STOP,
        "fixture",
        str(uuid4()),
    )


def test_chronological_split_never_shuffles_or_overlaps() -> None:
    result = chronological_split(tuple(range(10)))
    assert result.train == tuple(range(6))
    assert result.validation == (6, 7)
    assert result.test == (8, 9)
    assert max(result.train) < min(result.validation) < min(result.test)
    with pytest.raises(ValueError, match="below 1"):
        chronological_split(
            tuple(range(10)), train_fraction=Decimal("0.8"), validation_fraction=Decimal("0.2")
        )


def test_walk_forward_folds_are_ordered_and_support_expanding_or_rolling_windows() -> None:
    values = tuple(range(12))
    expanding = walk_forward_folds(
        values, train_size=4, validation_size=2, test_size=2, step_size=2
    )
    assert expanding[0].train == tuple(range(4))
    assert expanding[0].validation == (4, 5)
    assert expanding[0].test == (6, 7)
    assert expanding[1].train == tuple(range(6))
    rolling = walk_forward_folds(
        values, train_size=4, validation_size=2, test_size=2, step_size=2, expanding=False
    )
    assert rolling[1].train == (2, 3, 4, 5)
    assert rolling[1].validation == (6, 7)
    assert rolling[1].test == (8, 9)


def test_monte_carlo_is_seeded_and_reports_sequence_drawdown_not_fake_profit() -> None:
    pnls = (Decimal("100"), Decimal("-80"), Decimal("50"), Decimal("-20"))
    first = monte_carlo_trade_sequences(
        pnls, initial_capital=Decimal("1000"), simulations=100, seed=11
    )
    second = monte_carlo_trade_sequences(
        pnls, initial_capital=Decimal("1000"), simulations=100, seed=11
    )
    assert first == second
    assert first.median_final_equity == Decimal("1050")
    assert first.worst_maximum_drawdown > 0
    assert first.probability_of_loss == 0


def test_parameter_stability_rejects_an_isolated_optimum() -> None:
    stable = assess_parameter_stability(
        (Decimal("1"), Decimal("1.1"), Decimal("0.9"), Decimal("1.05"))
    )
    unstable = assess_parameter_stability(
        (Decimal("0.1"), Decimal("5"), Decimal("0.1")), maximum_neighbor_change=Decimal("0.5")
    )
    assert stable.stable is True
    assert unstable.stable is False
    assert unstable.maximum_neighbor_change > Decimal("0.5")


def test_cost_sensitivity_and_benchmark_comparison_are_explicit() -> None:
    trades = (trade("100"), trade("-20"))
    sensitivity = cost_sensitivity(trades, (Decimal(0), Decimal("100")))
    assert sensitivity[0].adjusted_net_profit == Decimal("80")
    assert sensitivity[0].profitable is True
    assert sensitivity[1].adjusted_net_profit < sensitivity[0].adjusted_net_profit
    comparison = compare_benchmark(
        (Decimal("100"), Decimal("110")), (Decimal("100"), Decimal("105"))
    )
    assert comparison.strategy_return == Decimal("0.1")
    assert comparison.benchmark_return == Decimal("0.05")
    assert comparison.excess_return == Decimal("0.05")
