from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from packages.domain.models import OrderStatus
from packages.execution import (
    OrderEvent,
    OrderEventType,
    OrderState,
    apply_order_event,
    initial_order_state,
)

NOW = datetime(2026, 9, 18, 5, tzinfo=UTC)


def advance(
    state: OrderState,
    event_type: OrderEventType,
    index: int,
    *,
    broker_order_id: str | None = None,
) -> OrderState:
    return apply_order_event(
        state,
        OrderEvent(
            f"event-{index}",
            event_type,
            NOW + timedelta(seconds=index),
            broker_order_id=broker_order_id,
        ),
    )


def submitted_state() -> OrderState:
    state = initial_order_state(uuid4(), Decimal(10), NOW)
    state = advance(state, OrderEventType.RISK_REQUESTED, 1)
    state = advance(state, OrderEventType.RISK_APPROVED, 2)
    state = advance(state, OrderEventType.SUBMIT_STARTED, 3)
    return advance(state, OrderEventType.SUBMIT_CONFIRMED, 4, broker_order_id="broker-order-1")


def test_partial_and_complete_fills_are_cumulative_and_idempotent() -> None:
    state = submitted_state()
    first_fill = OrderEvent("fill-1", OrderEventType.FILL, NOW + timedelta(seconds=5), Decimal(4))
    partial = apply_order_event(state, first_fill)
    assert partial.status is OrderStatus.PARTIALLY_FILLED
    assert partial.filled_quantity == 4
    assert apply_order_event(partial, first_fill) is partial
    filled = apply_order_event(
        partial,
        OrderEvent("fill-2", OrderEventType.FILL, NOW + timedelta(seconds=6), Decimal(6)),
    )
    assert filled.status is OrderStatus.FILLED
    assert filled.filled_quantity == 10


def test_unknown_submission_requires_reconciliation_and_cannot_be_resubmitted() -> None:
    state = initial_order_state(uuid4(), Decimal(1), NOW)
    state = advance(state, OrderEventType.RISK_REQUESTED, 1)
    state = advance(state, OrderEventType.RISK_APPROVED, 2)
    state = advance(state, OrderEventType.SUBMIT_STARTED, 3)
    unknown = advance(state, OrderEventType.SUBMISSION_UNKNOWN, 4)
    assert unknown.status is OrderStatus.RECONCILIATION_REQUIRED
    with pytest.raises(ValueError, match="invalid"):
        advance(unknown, OrderEventType.SUBMIT_STARTED, 5)


def test_out_of_order_conflicting_and_overfill_events_fail_closed() -> None:
    state = submitted_state()
    old = apply_order_event(
        state,
        OrderEvent("old", OrderEventType.BROKER_ACKNOWLEDGED, NOW),
    )
    assert old.status is OrderStatus.RECONCILIATION_REQUIRED
    assert old.reconciliation_reason == "OUT_OF_ORDER_EVENT"
    conflict = apply_order_event(
        state,
        OrderEvent(
            "conflict",
            OrderEventType.BROKER_ACKNOWLEDGED,
            NOW + timedelta(seconds=5),
            broker_order_id="other-order",
        ),
    )
    assert conflict.status is OrderStatus.RECONCILIATION_REQUIRED
    assert conflict.reconciliation_reason == "CONFLICTING_BROKER_ORDER_ID"
    overfill = apply_order_event(
        state,
        OrderEvent("overfill", OrderEventType.FILL, NOW + timedelta(seconds=5), Decimal(11)),
    )
    assert overfill.status is OrderStatus.RECONCILIATION_REQUIRED
    assert overfill.reconciliation_reason == "OVERFILL"


def test_partial_fill_can_be_cancelled_without_losing_filled_quantity() -> None:
    state = submitted_state()
    state = apply_order_event(
        state,
        OrderEvent("fill", OrderEventType.FILL, NOW + timedelta(seconds=5), Decimal(4)),
    )
    state = advance(state, OrderEventType.CANCEL_REQUESTED, 6)
    state = advance(state, OrderEventType.CANCEL_CONFIRMED, 7)
    assert state.status is OrderStatus.CANCELLED
    assert state.filled_quantity == 4
