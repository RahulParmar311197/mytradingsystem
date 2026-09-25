"""Strategy-independent, deterministic pre-trade risk evaluation."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from packages.domain.models import OrderIntent, RiskDecision, RiskOutcome


@dataclass(frozen=True, slots=True)
class RiskLimits:
    policy_version: str
    maximum_risk_per_trade_fraction: Decimal
    maximum_daily_loss_fraction: Decimal
    maximum_open_positions: int
    maximum_instrument_exposure_fraction: Decimal
    maximum_quote_age_seconds: int
    maximum_spread_bps: Decimal
    maximum_weekly_loss_fraction: Decimal = Decimal(1)
    maximum_drawdown_fraction: Decimal = Decimal(1)
    maximum_gross_exposure_fraction: Decimal = Decimal(1)
    maximum_net_exposure_fraction: Decimal = Decimal(1)
    maximum_orders_per_minute: int = 1_000_000
    maximum_consecutive_losses: int = 1_000_000
    maximum_sector_exposure_fraction: Decimal = Decimal(1)
    maximum_strategy_allocation_fraction: Decimal = Decimal(1)
    maximum_slippage_bps: Decimal = Decimal("1000000")
    maximum_options_exposure: Decimal = Decimal("1E+50")
    maximum_portfolio_delta: Decimal = Decimal("1E+50")
    maximum_portfolio_gamma: Decimal = Decimal("1E+50")

    def __post_init__(self) -> None:
        fractions = (
            self.maximum_risk_per_trade_fraction,
            self.maximum_daily_loss_fraction,
            self.maximum_instrument_exposure_fraction,
            self.maximum_weekly_loss_fraction,
            self.maximum_drawdown_fraction,
            self.maximum_gross_exposure_fraction,
            self.maximum_net_exposure_fraction,
            self.maximum_sector_exposure_fraction,
            self.maximum_strategy_allocation_fraction,
        )
        if not self.policy_version.strip():
            raise ValueError("risk policy version cannot be empty")
        if any(value <= 0 or value > 1 for value in fractions):
            raise ValueError("risk fractions must be in (0, 1]")
        integer_limits = (
            self.maximum_open_positions,
            self.maximum_quote_age_seconds,
            self.maximum_orders_per_minute,
            self.maximum_consecutive_losses,
        )
        if any(value <= 0 for value in integer_limits):
            raise ValueError("integer risk limits must be positive")
        if self.maximum_spread_bps < 0 or self.maximum_slippage_bps < 0:
            raise ValueError("spread and slippage limits cannot be negative")
        if (
            min(
                self.maximum_options_exposure,
                self.maximum_portfolio_delta,
                self.maximum_portfolio_gamma,
            )
            <= 0
        ):
            raise ValueError("options risk limits must be positive")


@dataclass(frozen=True, slots=True)
class PortfolioRiskContext:
    evaluated_at: datetime
    equity: Decimal
    daily_pnl: Decimal
    open_positions: int
    instrument_exposure: Decimal
    current_position_quantity: Decimal
    quote_timestamp: datetime
    bid: Decimal
    ask: Decimal
    broker_connected: bool
    data_quality_ok: bool
    trading_session_open: bool
    event_risk_lock: bool = False
    kill_switch_enabled: bool = False
    weekly_pnl: Decimal = Decimal(0)
    drawdown_fraction: Decimal = Decimal(0)
    gross_exposure: Decimal = Decimal(0)
    net_exposure: Decimal = Decimal(0)
    orders_last_minute: int = 0
    consecutive_losses: int = 0
    sector_exposure: Decimal = Decimal(0)
    strategy_exposure: Decimal = Decimal(0)
    expected_slippage_bps: Decimal = Decimal(0)
    cooldown_until: datetime | None = None
    reconciliation_ok: bool = True
    options_exposure: Decimal = Decimal(0)
    proposed_options_exposure: Decimal = Decimal(0)
    portfolio_delta: Decimal = Decimal(0)
    proposed_delta: Decimal = Decimal(0)
    portfolio_gamma: Decimal = Decimal(0)
    proposed_gamma: Decimal = Decimal(0)

    def __post_init__(self) -> None:
        for timestamp in (self.evaluated_at, self.quote_timestamp):
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError("risk timestamps must be timezone-aware")
        if min(self.open_positions, self.orders_last_minute, self.consecutive_losses) < 0:
            raise ValueError("risk counters cannot be negative")
        if self.drawdown_fraction < 0:
            raise ValueError("drawdown cannot be negative")
        if self.expected_slippage_bps < 0:
            raise ValueError("expected slippage cannot be negative")
        if self.options_exposure < 0 or self.proposed_options_exposure < 0:
            raise ValueError("options exposure cannot be negative")
        if self.cooldown_until is not None and (
            self.cooldown_until.tzinfo is None or self.cooldown_until.utcoffset() is None
        ):
            raise ValueError("cooldown timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True)
class RiskEvaluationRequest:
    intent: OrderIntent
    context: PortfolioRiskContext
    limits: RiskLimits
    reference_price: Decimal
    stop_price: Decimal | None


def _decision(
    request: RiskEvaluationRequest,
    outcome: RiskOutcome,
    quantity: Decimal,
    *reasons: str,
) -> RiskDecision:
    return RiskDecision(
        order_intent_id=request.intent.id,
        timestamp=request.context.evaluated_at,
        outcome=outcome,
        approved_quantity=quantity,
        reason_codes=tuple(reasons),
        risk_policy_version=request.limits.policy_version,
    )


def evaluate_order_risk(request: RiskEvaluationRequest) -> RiskDecision:
    """Approve, resize, or reject an intent; entry locks never suppress a valid exit."""
    intent, context, limits = request.intent, request.context, request.limits
    if context.equity <= 0 or request.reference_price <= 0:
        return _decision(request, RiskOutcome.REJECTED, Decimal(0), "INVALID_CAPITAL_OR_PRICE")
    if context.bid <= 0 or context.ask < context.bid:
        return _decision(request, RiskOutcome.REJECTED, Decimal(0), "INVALID_QUOTE")

    if intent.is_exit:
        available = abs(context.current_position_quantity)
        if available <= 0:
            return _decision(request, RiskOutcome.REJECTED, Decimal(0), "NO_POSITION_TO_EXIT")
        quantity = min(intent.quantity, available)
        outcome = RiskOutcome.APPROVED if quantity == intent.quantity else RiskOutcome.RESIZED
        reason = "EXIT_APPROVED" if outcome is RiskOutcome.APPROVED else "EXIT_RESIZED_TO_POSITION"
        return _decision(request, outcome, quantity, reason)

    locks: list[str] = []
    if context.kill_switch_enabled:
        locks.append("KILL_SWITCH")
    if not context.broker_connected:
        locks.append("BROKER_DISCONNECTED")
    if not context.reconciliation_ok:
        locks.append("RECONCILIATION_UNCERTAIN")
    if not context.data_quality_ok:
        locks.append("DATA_QUALITY_LOCK")
    if not context.trading_session_open:
        locks.append("OUTSIDE_TRADING_SESSION")
    if context.event_risk_lock:
        locks.append("EVENT_RISK_LOCK")
    quote_age = (context.evaluated_at - context.quote_timestamp).total_seconds()
    if quote_age < 0 or quote_age > limits.maximum_quote_age_seconds:
        locks.append("STALE_QUOTE")
    mid = (context.bid + context.ask) / 2
    spread_bps = (context.ask - context.bid) / mid * 10000
    if spread_bps > limits.maximum_spread_bps:
        locks.append("ABNORMAL_SPREAD")
    if context.daily_pnl <= -(context.equity * limits.maximum_daily_loss_fraction):
        locks.append("MAXIMUM_DAILY_LOSS")
    if context.weekly_pnl <= -(context.equity * limits.maximum_weekly_loss_fraction):
        locks.append("MAXIMUM_WEEKLY_LOSS")
    if context.drawdown_fraction >= limits.maximum_drawdown_fraction:
        locks.append("MAXIMUM_DRAWDOWN")
    if context.open_positions >= limits.maximum_open_positions:
        locks.append("MAXIMUM_OPEN_POSITIONS")
    if context.gross_exposure >= context.equity * limits.maximum_gross_exposure_fraction:
        locks.append("MAXIMUM_GROSS_EXPOSURE")
    if abs(context.net_exposure) >= context.equity * limits.maximum_net_exposure_fraction:
        locks.append("MAXIMUM_NET_EXPOSURE")
    if context.orders_last_minute >= limits.maximum_orders_per_minute:
        locks.append("MAXIMUM_ORDER_RATE")
    if context.consecutive_losses >= limits.maximum_consecutive_losses:
        locks.append("CONSECUTIVE_LOSS_CIRCUIT_BREAKER")
    if context.sector_exposure >= context.equity * limits.maximum_sector_exposure_fraction:
        locks.append("MAXIMUM_SECTOR_EXPOSURE")
    if context.strategy_exposure >= context.equity * limits.maximum_strategy_allocation_fraction:
        locks.append("MAXIMUM_STRATEGY_ALLOCATION")
    if context.expected_slippage_bps > limits.maximum_slippage_bps:
        locks.append("SLIPPAGE_THRESHOLD")
    if (
        context.options_exposure + context.proposed_options_exposure
        > limits.maximum_options_exposure
    ):
        locks.append("MAXIMUM_OPTIONS_EXPOSURE")
    if abs(context.portfolio_delta + context.proposed_delta) > limits.maximum_portfolio_delta:
        locks.append("MAXIMUM_PORTFOLIO_DELTA")
    if abs(context.portfolio_gamma + context.proposed_gamma) > limits.maximum_portfolio_gamma:
        locks.append("MAXIMUM_PORTFOLIO_GAMMA")
    if context.cooldown_until is not None and context.evaluated_at < context.cooldown_until:
        locks.append("RISK_COOLDOWN")
    if locks:
        return _decision(request, RiskOutcome.REJECTED, Decimal(0), *locks)

    if request.stop_price is None:
        return _decision(request, RiskOutcome.REJECTED, Decimal(0), "STOP_REQUIRED")
    stop_distance = abs(request.reference_price - request.stop_price)
    if stop_distance <= 0:
        return _decision(request, RiskOutcome.REJECTED, Decimal(0), "INVALID_STOP_DISTANCE")
    risk_quantity = context.equity * limits.maximum_risk_per_trade_fraction / stop_distance
    exposure_limit = context.equity * limits.maximum_instrument_exposure_fraction
    exposure_headroom = max(Decimal(0), exposure_limit - abs(context.instrument_exposure))
    exposure_quantity = exposure_headroom / request.reference_price
    approved = min(intent.quantity, risk_quantity, exposure_quantity)
    if approved <= 0:
        return _decision(request, RiskOutcome.REJECTED, Decimal(0), "NO_EXPOSURE_CAPACITY")
    if approved < intent.quantity:
        return _decision(request, RiskOutcome.RESIZED, approved, "POSITION_SIZE_REDUCED")
    return _decision(request, RiskOutcome.APPROVED, approved, "APPROVED")
