"""Deterministic order lifecycle with idempotent broker-event handling."""

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from packages.domain.models import OrderStatus


class OrderEventType(StrEnum):
    RISK_REQUESTED = "RISK_REQUESTED"
    RISK_APPROVED = "RISK_APPROVED"
    RISK_REJECTED = "RISK_REJECTED"
    SUBMIT_STARTED = "SUBMIT_STARTED"
    SUBMIT_CONFIRMED = "SUBMIT_CONFIRMED"
    SUBMISSION_UNKNOWN = "SUBMISSION_UNKNOWN"
    BROKER_ACKNOWLEDGED = "BROKER_ACKNOWLEDGED"
    FILL = "FILL"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCEL_CONFIRMED = "CANCEL_CONFIRMED"
    BROKER_REJECTED = "BROKER_REJECTED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class OrderEvent:
    event_id: str
    event_type: OrderEventType
    occurred_at: datetime
    fill_quantity: Decimal = Decimal(0)
    broker_order_id: str | None = None

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("order event ID cannot be empty")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("order event timestamp must be timezone-aware")
        if self.fill_quantity < 0:
            raise ValueError("fill quantity cannot be negative")
        if self.event_type is OrderEventType.FILL and self.fill_quantity <= 0:
            raise ValueError("fill events require positive quantity")
        if self.event_type is not OrderEventType.FILL and self.fill_quantity != 0:
            raise ValueError("only fill events may carry fill quantity")


@dataclass(frozen=True, slots=True)
class OrderState:
    order_id: UUID
    quantity: Decimal
    status: OrderStatus
    filled_quantity: Decimal
    broker_order_id: str | None
    last_event_at: datetime
    processed_event_ids: frozenset[str]
    version: int
    reconciliation_reason: str | None


def initial_order_state(order_id: UUID, quantity: Decimal, created_at: datetime) -> OrderState:
    if quantity <= 0:
        raise ValueError("order quantity must be positive")
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("order creation timestamp must be timezone-aware")
    return OrderState(
        order_id,
        quantity,
        OrderStatus.CREATED,
        Decimal(0),
        None,
        created_at,
        frozenset(),
        0,
        None,
    )


_TRANSITIONS: dict[tuple[OrderStatus, OrderEventType], OrderStatus] = {
    (OrderStatus.CREATED, OrderEventType.RISK_REQUESTED): OrderStatus.RISK_PENDING,
    (OrderStatus.RISK_PENDING, OrderEventType.RISK_APPROVED): OrderStatus.APPROVED,
    (OrderStatus.RISK_PENDING, OrderEventType.RISK_REJECTED): OrderStatus.RISK_REJECTED,
    (OrderStatus.APPROVED, OrderEventType.SUBMIT_STARTED): OrderStatus.SUBMITTING,
    (OrderStatus.SUBMITTING, OrderEventType.SUBMIT_CONFIRMED): OrderStatus.SUBMITTED,
    (
        OrderStatus.SUBMITTING,
        OrderEventType.SUBMISSION_UNKNOWN,
    ): OrderStatus.RECONCILIATION_REQUIRED,
    (OrderStatus.SUBMITTED, OrderEventType.BROKER_ACKNOWLEDGED): OrderStatus.ACKNOWLEDGED,
    (OrderStatus.SUBMITTED, OrderEventType.BROKER_REJECTED): OrderStatus.REJECTED,
    (OrderStatus.ACKNOWLEDGED, OrderEventType.BROKER_REJECTED): OrderStatus.REJECTED,
    (OrderStatus.SUBMITTED, OrderEventType.CANCEL_REQUESTED): OrderStatus.CANCEL_PENDING,
    (OrderStatus.ACKNOWLEDGED, OrderEventType.CANCEL_REQUESTED): OrderStatus.CANCEL_PENDING,
    (OrderStatus.PARTIALLY_FILLED, OrderEventType.CANCEL_REQUESTED): OrderStatus.CANCEL_PENDING,
    (OrderStatus.CANCEL_PENDING, OrderEventType.CANCEL_CONFIRMED): OrderStatus.CANCELLED,
    (OrderStatus.SUBMITTED, OrderEventType.EXPIRED): OrderStatus.EXPIRED,
    (OrderStatus.ACKNOWLEDGED, OrderEventType.EXPIRED): OrderStatus.EXPIRED,
}

_FILLABLE = {
    OrderStatus.SUBMITTED,
    OrderStatus.ACKNOWLEDGED,
    OrderStatus.PARTIALLY_FILLED,
    OrderStatus.CANCEL_PENDING,
}


def apply_order_event(state: OrderState, event: OrderEvent) -> OrderState:
    """Apply once; unsafe/out-of-order events fail closed instead of inventing broker truth."""
    if event.event_id in state.processed_event_ids:
        return state
    if event.occurred_at < state.last_event_at:
        return _requires_reconciliation(state, event, "OUT_OF_ORDER_EVENT")
    broker_order_id = state.broker_order_id
    if event.broker_order_id is not None:
        if broker_order_id is not None and broker_order_id != event.broker_order_id:
            return _requires_reconciliation(state, event, "CONFLICTING_BROKER_ORDER_ID")
        broker_order_id = event.broker_order_id

    status = state.status
    filled = state.filled_quantity
    if event.event_type is OrderEventType.FILL:
        if status not in _FILLABLE:
            raise ValueError(f"fill is invalid from order state {status.value}")
        filled += event.fill_quantity
        if filled > state.quantity:
            return _requires_reconciliation(state, event, "OVERFILL")
        status = OrderStatus.FILLED if filled == state.quantity else OrderStatus.PARTIALLY_FILLED
    else:
        target = _TRANSITIONS.get((status, event.event_type))
        if target is None:
            raise ValueError(
                f"event {event.event_type.value} is invalid from order state {status.value}"
            )
        status = target
    reconciliation_reason = (
        "SUBMISSION_OUTCOME_UNKNOWN"
        if status is OrderStatus.RECONCILIATION_REQUIRED
        else state.reconciliation_reason
    )
    return replace(
        state,
        status=status,
        filled_quantity=filled,
        broker_order_id=broker_order_id,
        last_event_at=event.occurred_at,
        processed_event_ids=state.processed_event_ids | {event.event_id},
        version=state.version + 1,
        reconciliation_reason=reconciliation_reason,
    )


def _requires_reconciliation(state: OrderState, event: OrderEvent, reason: str) -> OrderState:
    return replace(
        state,
        status=OrderStatus.RECONCILIATION_REQUIRED,
        last_event_at=max(state.last_event_at, event.occurred_at),
        processed_event_ids=state.processed_event_ids | {event.event_id},
        version=state.version + 1,
        reconciliation_reason=reason,
    )
