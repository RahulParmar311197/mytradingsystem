from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from packages.domain.models import OrderStatus
from packages.execution import (
    BrokerOrderSnapshot,
    OrderState,
    ReconciliationIssueType,
    initial_order_state,
    reconcile_orders,
)

NOW = datetime(2026, 9, 19, 5, tzinfo=UTC)


def local(
    broker_id: str | None = "broker-1",
    status: OrderStatus = OrderStatus.ACKNOWLEDGED,
    filled: Decimal = Decimal(0),
) -> OrderState:
    return replace(
        initial_order_state(uuid4(), Decimal(10), NOW),
        broker_order_id=broker_id,
        status=status,
        filled_quantity=filled,
    )


def test_exact_broker_and_local_state_is_safe() -> None:
    result = reconcile_orders(
        (local(),),
        (BrokerOrderSnapshot("broker-1", OrderStatus.ACKNOWLEDGED, Decimal(10), Decimal(0)),),
    )
    assert result.safe_to_trade is True
    assert result.matched_orders == 1
    assert result.issues == ()


def test_unknown_missing_duplicate_and_mismatched_orders_lock_trading() -> None:
    duplicate_local = local("broker-1")
    result = reconcile_orders(
        (
            local("broker-1", OrderStatus.PARTIALLY_FILLED, Decimal(4)),
            duplicate_local,
            local("broker-missing"),
            local(None, OrderStatus.RECONCILIATION_REQUIRED),
        ),
        (
            BrokerOrderSnapshot("broker-1", OrderStatus.FILLED, Decimal(10), Decimal(10)),
            BrokerOrderSnapshot("broker-unknown", OrderStatus.ACKNOWLEDGED, Decimal(1), Decimal(0)),
            BrokerOrderSnapshot("broker-unknown", OrderStatus.ACKNOWLEDGED, Decimal(1), Decimal(0)),
        ),
    )
    issue_types = {issue.issue_type for issue in result.issues}
    assert result.safe_to_trade is False
    assert issue_types == {
        ReconciliationIssueType.UNKNOWN_BROKER_ORDER,
        ReconciliationIssueType.MISSING_BROKER_ORDER,
        ReconciliationIssueType.DUPLICATE_BROKER_ORDER,
        ReconciliationIssueType.FILLED_QUANTITY_MISMATCH,
        ReconciliationIssueType.STATUS_MISMATCH,
    }


def test_pre_broker_local_states_do_not_require_broker_identity() -> None:
    result = reconcile_orders(
        (local(None, OrderStatus.RISK_PENDING),),
        (),
    )
    assert result.safe_to_trade is True
