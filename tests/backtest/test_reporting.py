from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfoNotFoundError

import pytest

from packages.backtesting import (
    BacktestResult,
    BacktestTrade,
    ExitReason,
    PerformanceMetrics,
    build_performance_report,
)
from packages.domain.models import SignalAction


def result_fixture() -> BacktestResult:
    start = datetime(2026, 1, 31, 18, 29, tzinfo=UTC)  # 23:59 IST
    curve = (
        (start, Decimal("100")),
        (start + timedelta(minutes=2), Decimal("90")),
        (start + timedelta(days=1), Decimal("110")),
    )
    trade = BacktestTrade(
        SignalAction.LONG,
        Decimal(1),
        start,
        start,
        start + timedelta(hours=12),
        Decimal("100"),
        Decimal("111"),
        Decimal("95"),
        Decimal("110"),
        Decimal("11"),
        Decimal("1"),
        Decimal("10"),
        ExitReason.TARGET,
        "fixture",
        "snapshot-1",
    )
    metrics = PerformanceMetrics(
        Decimal("10"),
        Decimal("0.1"),
        Decimal(1),
        Decimal("10"),
        Decimal(0),
        Decimal("10"),
        None,
        Decimal("0.1"),
        None,
        Decimal("211"),
        1,
        1,
        0,
    )
    return BacktestResult(Decimal("100"), Decimal("110"), curve, (), (trade,), (), metrics)


def test_report_uses_ist_period_boundaries_and_direction_breakdown() -> None:
    report = build_performance_report(result_fixture())
    assert [item.period for item in report.daily_returns] == ["2026-01-31", "2026-02-01"]
    assert report.daily_returns[0].return_fraction == Decimal(0)
    assert report.daily_returns[1].return_fraction == Decimal("0.1")
    assert [item.period for item in report.monthly_returns] == ["2026-01", "2026-02"]
    assert report.by_direction[0].direction is SignalAction.LONG
    assert report.by_direction[0].net_profit == Decimal("10")
    assert Decimal(0) < report.exposure_fraction < Decimal(1)
    assert report.sortino_ratio is not None
    assert report.calmar_ratio is not None


def test_report_validates_annualization_and_timezone() -> None:
    with pytest.raises(ValueError, match="annualization"):
        build_performance_report(result_fixture(), annualization_periods=0)
    with pytest.raises(ZoneInfoNotFoundError, match="Not/AZone"):
        build_performance_report(result_fixture(), presentation_timezone="Not/AZone")
