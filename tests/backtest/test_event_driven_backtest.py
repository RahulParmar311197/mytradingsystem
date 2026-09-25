from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from packages.backtesting import (
    BacktestConfig,
    BacktestRiskDecision,
    ExitReason,
    run_backtest,
)
from packages.decision_engine import DecisionResult
from packages.domain.models import Candle, Side, SignalAction

INSTRUMENT = uuid4()
START = datetime(2026, 9, 18, 4, tzinfo=UTC)


def candle(index: int, open_: str, high: str, low: str, close: str) -> Candle:
    return Candle(
        instrument_id=INSTRUMENT,
        timestamp=START + timedelta(minutes=index),
        timeframe_seconds=60,
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal("1000"),
    )


def decision(action: SignalAction, timestamp: datetime) -> DecisionResult:
    entry = action in (SignalAction.LONG, SignalAction.SHORT)
    return DecisionResult(
        uuid4(),
        timestamp,
        INSTRUMENT,
        "fixture_strategy",
        "1.0.0",
        "decision-rules-v1",
        action,
        Decimal("0.8"),
        {"fixture": Decimal(1)},
        (),
        Decimal("100") if entry else None,
        Decimal("98") if action is SignalAction.LONG else Decimal("102") if entry else None,
        (Decimal("104"),) if action is SignalAction.LONG else (Decimal("96"),) if entry else (),
        Decimal("2") if entry else None,
        Decimal("0.01") if entry else Decimal(0),
        "snapshot-fixture",
        entry,
        "fixture",
    )


def no_trade(history: tuple[Candle, ...]) -> DecisionResult:
    return decision(SignalAction.NO_TRADE, history[-1].timestamp)


def test_signal_is_filled_only_at_next_candle_open_and_target_is_costed() -> None:
    source = (
        candle(0, "100", "101", "99", "100"),
        candle(1, "100", "101", "99", "100"),
        candle(2, "102", "105", "101", "104"),
    )

    def provider(history: tuple[Candle, ...]) -> DecisionResult:
        return (
            decision(SignalAction.LONG, history[-1].timestamp)
            if len(history) == 2
            else no_trade(history)
        )

    result = run_backtest(
        source,
        provider,
        BacktestConfig(
            slippage_bps=Decimal(0), variable_cost_bps=Decimal(0), flat_cost_per_order=Decimal(0)
        ),
    )
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.signal_at == source[1].timestamp
    assert trade.entered_at == source[2].timestamp
    assert trade.entry_price == Decimal("102")
    assert trade.exit_price == Decimal("104")
    assert trade.exit_reason is ExitReason.TARGET
    assert trade.net_pnl > 0
    assert result.metrics.trade_count == 1
    assert result.metrics.win_rate == 1


def test_pluggable_cost_model_receives_entry_and_exit_sides() -> None:
    class TrackingCosts:
        def __init__(self) -> None:
            self.sides: list[Side] = []

        def calculate(self, notional: Decimal, side: Side) -> Decimal:
            assert notional > 0
            self.sides.append(side)
            return Decimal("1")

    source = (
        candle(0, "100", "101", "99", "100"),
        candle(1, "100", "101", "99", "100"),
        candle(2, "100", "105", "99", "104"),
    )

    def provider(history: tuple[Candle, ...]) -> DecisionResult:
        return (
            decision(SignalAction.LONG, history[-1].timestamp)
            if len(history) == 2
            else no_trade(history)
        )

    costs = TrackingCosts()
    result = run_backtest(
        source, provider, BacktestConfig(slippage_bps=Decimal(0)), cost_model=costs
    )
    assert costs.sides == [Side.BUY, Side.SELL]
    assert result.trades[0].costs == Decimal("2")


def test_stop_wins_when_stop_and_target_are_touched_in_same_candle() -> None:
    source = (
        candle(0, "100", "101", "99", "100"),
        candle(1, "100", "101", "99", "100"),
        candle(2, "100", "105", "97", "101"),
    )

    def provider(history: tuple[Candle, ...]) -> DecisionResult:
        return (
            decision(SignalAction.LONG, history[-1].timestamp)
            if len(history) == 2
            else no_trade(history)
        )

    result = run_backtest(source, provider, BacktestConfig(slippage_bps=Decimal(0)))
    assert result.trades[0].exit_reason is ExitReason.STOP
    assert result.trades[0].exit_price == Decimal("98")
    assert result.trades[0].net_pnl < 0


def test_exit_signal_is_also_deferred_to_next_open() -> None:
    source = (
        candle(0, "100", "101", "99", "100"),
        candle(1, "100", "101", "99", "100"),
        candle(2, "100", "103", "99", "102"),
        candle(3, "103", "103", "102", "102"),
    )

    def provider(history: tuple[Candle, ...]) -> DecisionResult:
        if len(history) == 1:
            return decision(SignalAction.LONG, history[-1].timestamp)
        if len(history) == 3:
            return decision(SignalAction.EXIT, history[-1].timestamp)
        return no_trade(history)

    result = run_backtest(
        source,
        provider,
        BacktestConfig(
            slippage_bps=Decimal(0), variable_cost_bps=Decimal(0), flat_cost_per_order=Decimal(0)
        ),
    )
    trade = result.trades[0]
    assert trade.exit_reason is ExitReason.SIGNAL
    assert trade.exited_at == source[3].timestamp
    assert trade.exit_price == source[3].open


def test_risk_rejection_is_recorded_and_creates_no_position() -> None:
    class RejectAll:
        def evaluate(
            self, decision: DecisionResult, equity: Decimal, fill_price: Decimal
        ) -> BacktestRiskDecision:
            return BacktestRiskDecision(False, Decimal(0), "TEST_REJECTION")

    source = (candle(0, "100", "101", "99", "100"), candle(1, "100", "101", "99", "100"))

    def provider(history: tuple[Candle, ...]) -> DecisionResult:
        return (
            decision(SignalAction.LONG, history[-1].timestamp)
            if len(history) == 1
            else no_trade(history)
        )

    result = run_backtest(source, provider, risk_policy=RejectAll())
    assert result.trades == ()
    assert result.rejected_decisions == ((source[1].timestamp, "TEST_REJECTION"),)


def test_gap_beyond_stop_is_rejected_instead_of_using_invalid_geometry() -> None:
    source = (candle(0, "100", "101", "99", "100"), candle(1, "97", "98", "96", "97"))

    def provider(history: tuple[Candle, ...]) -> DecisionResult:
        return (
            decision(SignalAction.LONG, history[-1].timestamp)
            if len(history) == 1
            else no_trade(history)
        )

    result = run_backtest(source, provider)
    assert result.trades == ()
    assert result.rejected_decisions == ((source[1].timestamp, "STOP_INVALID_AT_FILL"),)


def test_provider_receives_only_current_prefix_and_open_candles_are_rejected() -> None:
    source = (candle(0, "100", "101", "99", "100"), candle(1, "100", "101", "99", "100"))
    observed: list[int] = []

    def provider(history: tuple[Candle, ...]) -> DecisionResult:
        observed.append(len(history))
        return no_trade(history)

    run_backtest(source, provider)
    assert observed == [1, 2]
    open_candle = source[0].model_copy(update={"is_closed": False})
    try:
        run_backtest((open_candle,), provider)
    except ValueError as error:
        assert "closed candles" in str(error)
    else:
        raise AssertionError("open candle should be rejected")
