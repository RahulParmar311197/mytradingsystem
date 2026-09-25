"""A conservative event-driven backtester with next-candle execution."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from math import sqrt
from typing import Protocol

from packages.decision_engine import DecisionResult
from packages.domain.models import Candle, Side, SignalAction


class ExitReason(StrEnum):
    STOP = "stop"
    TARGET = "target"
    SIGNAL = "signal"
    END_OF_DATA = "end_of_data"


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    initial_capital: Decimal = Decimal("1000000")
    slippage_bps: Decimal = Decimal("2")
    variable_cost_bps: Decimal = Decimal("3")
    flat_cost_per_order: Decimal = Decimal("20")
    maximum_position_notional_fraction: Decimal = Decimal("1")
    annualization_sessions: int = 252

    def __post_init__(self) -> None:
        if self.initial_capital <= 0:
            raise ValueError("initial capital must be positive")
        if any(
            value < 0
            for value in (self.slippage_bps, self.variable_cost_bps, self.flat_cost_per_order)
        ):
            raise ValueError("cost and slippage inputs cannot be negative")
        if not Decimal(0) < self.maximum_position_notional_fraction <= Decimal(1):
            raise ValueError("maximum notional fraction must be in (0, 1]")
        if self.annualization_sessions <= 0:
            raise ValueError("annualization sessions must be positive")


@dataclass(frozen=True, slots=True)
class BacktestRiskDecision:
    approved: bool
    quantity: Decimal
    reason: str


class BacktestRiskPolicy(Protocol):
    def evaluate(
        self, decision: DecisionResult, equity: Decimal, fill_price: Decimal
    ) -> BacktestRiskDecision: ...


class BacktestCostModel(Protocol):
    def calculate(self, notional: Decimal, side: Side) -> Decimal: ...


@dataclass(frozen=True, slots=True)
class GenericCostModel:
    variable_cost_bps: Decimal
    flat_cost_per_order: Decimal

    def calculate(self, notional: Decimal, side: Side) -> Decimal:
        del side
        return abs(notional) * self.variable_cost_bps / 10000 + self.flat_cost_per_order


@dataclass(frozen=True, slots=True)
class FixedFractionRiskPolicy:
    """Backtest-only sizing policy; it is not the production risk engine."""

    maximum_risk_fraction: Decimal = Decimal("0.01")
    maximum_notional_fraction: Decimal = Decimal("1")

    def evaluate(
        self, decision: DecisionResult, equity: Decimal, fill_price: Decimal
    ) -> BacktestRiskDecision:
        if not decision.requires_risk_approval:
            return BacktestRiskDecision(False, Decimal(0), "DECISION_NOT_ENTRY")
        if decision.proposed_stop is None or decision.requested_risk_fraction <= 0:
            return BacktestRiskDecision(False, Decimal(0), "INVALID_RISK_REQUEST")
        if (decision.action is SignalAction.LONG and decision.proposed_stop >= fill_price) or (
            decision.action is SignalAction.SHORT and decision.proposed_stop <= fill_price
        ):
            return BacktestRiskDecision(False, Decimal(0), "STOP_INVALID_AT_FILL")
        if not decision.proposed_targets or (
            (decision.action is SignalAction.LONG and decision.proposed_targets[0] <= fill_price)
            or (
                decision.action is SignalAction.SHORT and decision.proposed_targets[0] >= fill_price
            )
        ):
            return BacktestRiskDecision(False, Decimal(0), "TARGET_INVALID_AT_FILL")
        stop_distance = abs(fill_price - decision.proposed_stop)
        if stop_distance <= 0:
            return BacktestRiskDecision(False, Decimal(0), "INVALID_STOP_DISTANCE")
        risk_fraction = min(decision.requested_risk_fraction, self.maximum_risk_fraction)
        risk_quantity = equity * risk_fraction / stop_distance
        notional_quantity = equity * self.maximum_notional_fraction / fill_price
        quantity = min(risk_quantity, notional_quantity).to_integral_value(rounding="ROUND_FLOOR")
        if quantity <= 0:
            return BacktestRiskDecision(False, Decimal(0), "QUANTITY_BELOW_ONE")
        return BacktestRiskDecision(True, quantity, "APPROVED")


@dataclass(frozen=True, slots=True)
class BacktestTrade:
    direction: SignalAction
    quantity: Decimal
    signal_at: datetime
    entered_at: datetime
    exited_at: datetime
    entry_price: Decimal
    exit_price: Decimal
    stop: Decimal
    target: Decimal
    gross_pnl: Decimal
    costs: Decimal
    net_pnl: Decimal
    exit_reason: ExitReason
    strategy: str
    data_snapshot_id: str


@dataclass(frozen=True, slots=True)
class PerformanceMetrics:
    net_profit: Decimal
    total_return: Decimal
    win_rate: Decimal
    average_win: Decimal
    average_loss: Decimal
    expectancy: Decimal
    profit_factor: Decimal | None
    maximum_drawdown: Decimal
    sharpe_ratio: Decimal | None
    turnover: Decimal
    trade_count: int
    consecutive_wins: int
    consecutive_losses: int


@dataclass(frozen=True, slots=True)
class BacktestResult:
    initial_capital: Decimal
    final_equity: Decimal
    equity_curve: tuple[tuple[datetime, Decimal], ...]
    drawdown_curve: tuple[tuple[datetime, Decimal], ...]
    trades: tuple[BacktestTrade, ...]
    rejected_decisions: tuple[tuple[datetime, str], ...]
    metrics: PerformanceMetrics


@dataclass(slots=True)
class _Position:
    decision: DecisionResult
    direction: SignalAction
    quantity: Decimal
    signal_at: datetime
    entered_at: datetime
    entry_price: Decimal
    stop: Decimal
    target: Decimal
    entry_cost: Decimal


def _slipped(price: Decimal, action: SignalAction, bps: Decimal) -> Decimal:
    multiplier = Decimal(1) + (bps / 10000 if action is SignalAction.LONG else -bps / 10000)
    return price * multiplier


def _close_position(
    position: _Position,
    timestamp: datetime,
    raw_exit: Decimal,
    reason: ExitReason,
    config: BacktestConfig,
    cost_model: BacktestCostModel,
) -> BacktestTrade:
    exit_action = (
        SignalAction.SHORT if position.direction is SignalAction.LONG else SignalAction.LONG
    )
    exit_price = _slipped(raw_exit, exit_action, config.slippage_bps)
    sign = Decimal(1) if position.direction is SignalAction.LONG else Decimal(-1)
    gross = (exit_price - position.entry_price) * position.quantity * sign
    exit_side = Side.SELL if position.direction is SignalAction.LONG else Side.BUY
    exit_cost = cost_model.calculate(exit_price * position.quantity, exit_side)
    costs = position.entry_cost + exit_cost
    target = position.target
    return BacktestTrade(
        position.direction,
        position.quantity,
        position.signal_at,
        position.entered_at,
        timestamp,
        position.entry_price,
        exit_price,
        position.stop,
        target,
        gross,
        costs,
        gross - costs,
        reason,
        position.decision.strategy,
        position.decision.data_snapshot_id,
    )


def _intrabar_exit(position: _Position, candle: Candle) -> tuple[Decimal, ExitReason] | None:
    """Stops win ties when stop and target are both touched: conservative, never optimistic."""
    if position.direction is SignalAction.LONG:
        if candle.low <= position.stop:
            return min(candle.open, position.stop), ExitReason.STOP
        if candle.high >= position.target:
            return max(candle.open, position.target), ExitReason.TARGET
    else:
        if candle.high >= position.stop:
            return max(candle.open, position.stop), ExitReason.STOP
        if candle.low <= position.target:
            return min(candle.open, position.target), ExitReason.TARGET
    return None


def _metrics(
    initial: Decimal,
    equity_curve: list[tuple[datetime, Decimal]],
    drawdown_curve: list[tuple[datetime, Decimal]],
    trades: list[BacktestTrade],
    annualization: int,
) -> PerformanceMetrics:
    final = equity_curve[-1][1] if equity_curve else initial
    wins = [trade.net_pnl for trade in trades if trade.net_pnl > 0]
    losses = [trade.net_pnl for trade in trades if trade.net_pnl < 0]
    count = len(trades)
    win_rate = Decimal(len(wins)) / count if count else Decimal(0)
    average_win = sum(wins, Decimal(0)) / len(wins) if wins else Decimal(0)
    average_loss = sum(losses, Decimal(0)) / len(losses) if losses else Decimal(0)
    expectancy = (
        sum((trade.net_pnl for trade in trades), Decimal(0)) / count if count else Decimal(0)
    )
    gross_wins, gross_losses = sum(wins, Decimal(0)), abs(sum(losses, Decimal(0)))
    profit_factor = gross_wins / gross_losses if gross_losses else None
    maximum_drawdown = max((value for _, value in drawdown_curve), default=Decimal(0))
    returns = [
        float(equity_curve[index][1] / equity_curve[index - 1][1] - 1)
        for index in range(1, len(equity_curve))
        if equity_curve[index - 1][1] != 0
    ]
    sharpe: Decimal | None = None
    if len(returns) > 1:
        mean = sum(returns) / len(returns)
        variance = sum((item - mean) ** 2 for item in returns) / (len(returns) - 1)
        if variance > 0:
            sharpe = Decimal(str(mean / sqrt(variance) * sqrt(annualization)))
    consecutive_wins = consecutive_losses = current_wins = current_losses = 0
    for trade in trades:
        if trade.net_pnl > 0:
            current_wins, current_losses = current_wins + 1, 0
        elif trade.net_pnl < 0:
            current_losses, current_wins = current_losses + 1, 0
        consecutive_wins = max(consecutive_wins, current_wins)
        consecutive_losses = max(consecutive_losses, current_losses)
    turnover = sum(
        ((trade.entry_price + trade.exit_price) * trade.quantity for trade in trades), Decimal(0)
    )
    return PerformanceMetrics(
        final - initial,
        final / initial - 1,
        win_rate,
        average_win,
        average_loss,
        expectancy,
        profit_factor,
        maximum_drawdown,
        sharpe,
        turnover,
        count,
        consecutive_wins,
        consecutive_losses,
    )


DecisionProvider = Callable[[tuple[Candle, ...]], DecisionResult]


def run_backtest(
    candles: tuple[Candle, ...],
    decision_provider: DecisionProvider,
    config: BacktestConfig | None = None,
    risk_policy: BacktestRiskPolicy | None = None,
    cost_model: BacktestCostModel | None = None,
) -> BacktestResult:
    """Run decisions at close and execute queued actions on the next candle only."""
    settings = config or BacktestConfig()
    risk = risk_policy or FixedFractionRiskPolicy(
        maximum_notional_fraction=settings.maximum_position_notional_fraction
    )
    costs = cost_model or GenericCostModel(settings.variable_cost_bps, settings.flat_cost_per_order)
    if any(not candle.is_closed for candle in candles):
        raise ValueError("backtests accept closed candles only")
    if candles and any(
        candle.instrument_id != candles[0].instrument_id
        or candle.timeframe_seconds != candles[0].timeframe_seconds
        for candle in candles
    ):
        raise ValueError("candles must belong to one instrument and timeframe")
    if any(
        candles[index].timestamp <= candles[index - 1].timestamp for index in range(1, len(candles))
    ):
        raise ValueError("candles must be strictly chronological")
    equity = settings.initial_capital
    peak = equity
    position: _Position | None = None
    pending: DecisionResult | None = None
    trades: list[BacktestTrade] = []
    rejected: list[tuple[datetime, str]] = []
    equity_curve: list[tuple[datetime, Decimal]] = []
    drawdown_curve: list[tuple[datetime, Decimal]] = []

    for index, candle in enumerate(candles):
        if pending is not None:
            if position is not None and pending.action is SignalAction.EXIT:
                trade = _close_position(
                    position, candle.timestamp, candle.open, ExitReason.SIGNAL, settings, costs
                )
                trades.append(trade)
                equity += trade.net_pnl
                position = None
            elif position is None and pending.action in (SignalAction.LONG, SignalAction.SHORT):
                fill_price = _slipped(candle.open, pending.action, settings.slippage_bps)
                risk_result = risk.evaluate(pending, equity, fill_price)
                if (
                    risk_result.approved
                    and pending.proposed_stop is not None
                    and pending.proposed_targets
                ):
                    entry_side = Side.BUY if pending.action is SignalAction.LONG else Side.SELL
                    entry_cost = costs.calculate(fill_price * risk_result.quantity, entry_side)
                    position = _Position(
                        pending,
                        pending.action,
                        risk_result.quantity,
                        pending.timestamp,
                        candle.timestamp,
                        fill_price,
                        pending.proposed_stop,
                        pending.proposed_targets[0],
                        entry_cost,
                    )
                else:
                    rejected.append((candle.timestamp, risk_result.reason))
            pending = None

        if position is not None:
            exit_event = _intrabar_exit(position, candle)
            if exit_event is not None:
                trade = _close_position(position, candle.timestamp, *exit_event, settings, costs)
                trades.append(trade)
                equity += trade.net_pnl
                position = None

        decision = decision_provider(candles[: index + 1])
        if (position is not None and decision.action is SignalAction.EXIT) or (
            position is None and decision.action in (SignalAction.LONG, SignalAction.SHORT)
        ):
            pending = decision

        unrealized = Decimal(0)
        if position is not None:
            sign = Decimal(1) if position.direction is SignalAction.LONG else Decimal(-1)
            unrealized = (
                candle.close - position.entry_price
            ) * position.quantity * sign - position.entry_cost
        marked_equity = equity + unrealized
        peak = max(peak, marked_equity)
        drawdown = (peak - marked_equity) / peak if peak else Decimal(0)
        equity_curve.append((candle.timestamp, marked_equity))
        drawdown_curve.append((candle.timestamp, drawdown))

    if position is not None and candles:
        final_candle = candles[-1]
        trade = _close_position(
            position,
            final_candle.timestamp,
            final_candle.close,
            ExitReason.END_OF_DATA,
            settings,
            costs,
        )
        trades.append(trade)
        equity += trade.net_pnl
        equity_curve[-1] = (final_candle.timestamp, equity)
        peak = max(peak, equity)
        drawdown_curve[-1] = (
            final_candle.timestamp,
            (peak - equity) / peak if peak else Decimal(0),
        )

    metrics = _metrics(
        settings.initial_capital,
        equity_curve,
        drawdown_curve,
        trades,
        settings.annualization_sessions,
    )
    return BacktestResult(
        settings.initial_capital,
        equity,
        tuple(equity_curve),
        tuple(drawdown_curve),
        tuple(trades),
        tuple(rejected),
        metrics,
    )
