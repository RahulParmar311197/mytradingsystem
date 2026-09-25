from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from packages.domain.models import OrderIntent, OrderType, RiskOutcome, Side
from packages.risk_engine import (
    PortfolioRiskContext,
    RiskEvaluationRequest,
    RiskLimits,
    evaluate_order_risk,
)

NOW = datetime(2026, 9, 18, 5, tzinfo=UTC)


def request(*, exit_: bool = False, **changes: object) -> RiskEvaluationRequest:
    intent = OrderIntent(
        idempotency_key="risk-test-0001",
        decision_id=uuid4(),
        account_id=uuid4(),
        instrument_id=uuid4(),
        side=Side.SELL if exit_ else Side.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("1000"),
        created_at=NOW,
        is_exit=exit_,
    )
    context_values = {
        "evaluated_at": NOW,
        "equity": Decimal("100000"),
        "daily_pnl": Decimal(0),
        "open_positions": 1,
        "instrument_exposure": Decimal(0),
        "current_position_quantity": Decimal("50"),
        "quote_timestamp": NOW - timedelta(seconds=1),
        "bid": Decimal("99.95"),
        "ask": Decimal("100.05"),
        "broker_connected": True,
        "data_quality_ok": True,
        "trading_session_open": True,
        "event_risk_lock": False,
        "kill_switch_enabled": False,
    }
    context_values.update(changes)
    return RiskEvaluationRequest(
        intent,
        PortfolioRiskContext(**context_values),  # type: ignore[arg-type]
        RiskLimits(
            "risk-v1", Decimal("0.01"), Decimal("0.02"), 5, Decimal("0.2"), 5, Decimal("20")
        ),
        Decimal("100"),
        Decimal("98"),
    )


@pytest.mark.parametrize(
    ("change", "value", "reason"),
    [
        ("kill_switch_enabled", True, "KILL_SWITCH"),
        ("broker_connected", False, "BROKER_DISCONNECTED"),
        ("reconciliation_ok", False, "RECONCILIATION_UNCERTAIN"),
        ("data_quality_ok", False, "DATA_QUALITY_LOCK"),
        ("trading_session_open", False, "OUTSIDE_TRADING_SESSION"),
        ("event_risk_lock", True, "EVENT_RISK_LOCK"),
        ("open_positions", 5, "MAXIMUM_OPEN_POSITIONS"),
        ("daily_pnl", Decimal("-2000"), "MAXIMUM_DAILY_LOSS"),
        ("quote_timestamp", NOW - timedelta(seconds=6), "STALE_QUOTE"),
        ("weekly_pnl", Decimal("-100000"), "MAXIMUM_WEEKLY_LOSS"),
        ("drawdown_fraction", Decimal(1), "MAXIMUM_DRAWDOWN"),
        ("gross_exposure", Decimal("100000"), "MAXIMUM_GROSS_EXPOSURE"),
        ("net_exposure", Decimal("-100000"), "MAXIMUM_NET_EXPOSURE"),
        ("orders_last_minute", 1_000_000, "MAXIMUM_ORDER_RATE"),
        ("consecutive_losses", 1_000_000, "CONSECUTIVE_LOSS_CIRCUIT_BREAKER"),
        ("sector_exposure", Decimal("100000"), "MAXIMUM_SECTOR_EXPOSURE"),
        ("strategy_exposure", Decimal("100000"), "MAXIMUM_STRATEGY_ALLOCATION"),
        ("expected_slippage_bps", Decimal("1000001"), "SLIPPAGE_THRESHOLD"),
        ("cooldown_until", NOW + timedelta(minutes=1), "RISK_COOLDOWN"),
    ],
)
def test_new_entries_fail_closed_on_independent_locks(
    change: str, value: object, reason: str
) -> None:
    decision = evaluate_order_risk(request(**{change: value}))
    assert decision.outcome is RiskOutcome.REJECTED
    assert reason in decision.reason_codes
    assert decision.approved_quantity == 0


def test_risk_and_exposure_limits_resize_requested_quantity() -> None:
    decision = evaluate_order_risk(request())
    assert decision.outcome is RiskOutcome.RESIZED
    assert decision.approved_quantity == Decimal("200")
    assert decision.approved_quantity <= Decimal("500")


def test_kill_switch_preserves_bounded_exit_path() -> None:
    decision = evaluate_order_risk(request(exit_=True, kill_switch_enabled=True))
    assert decision.outcome is RiskOutcome.RESIZED
    assert decision.approved_quantity == Decimal("50")
    assert decision.reason_codes == ("EXIT_RESIZED_TO_POSITION",)


@pytest.mark.parametrize(
    ("context_changes", "limit_changes", "reason"),
    [
        (
            {"options_exposure": Decimal(900), "proposed_options_exposure": Decimal(101)},
            {"maximum_options_exposure": Decimal(1000)},
            "MAXIMUM_OPTIONS_EXPOSURE",
        ),
        (
            {"portfolio_delta": Decimal(-90), "proposed_delta": Decimal(-11)},
            {"maximum_portfolio_delta": Decimal(100)},
            "MAXIMUM_PORTFOLIO_DELTA",
        ),
        (
            {"portfolio_gamma": Decimal(9), "proposed_gamma": Decimal(2)},
            {"maximum_portfolio_gamma": Decimal(10)},
            "MAXIMUM_PORTFOLIO_GAMMA",
        ),
    ],
)
def test_projected_options_risk_limits_fail_closed(
    context_changes: dict[str, Decimal], limit_changes: dict[str, Decimal], reason: str
) -> None:
    original = request()
    changed = replace(
        original,
        context=replace(original.context, **context_changes),
        limits=replace(original.limits, **limit_changes),
    )
    decision = evaluate_order_risk(changed)
    assert decision.outcome is RiskOutcome.REJECTED
    assert reason in decision.reason_codes
