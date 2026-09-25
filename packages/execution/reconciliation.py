"""Broker/local order reconciliation that fails closed on uncertain truth."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from packages.domain.models import OrderStatus
from packages.execution.state_machine import OrderState


class ReconciliationIssueType(StrEnum):
    UNKNOWN_BROKER_ORDER = "UNKNOWN_BROKER_ORDER"
    MISSING_BROKER_ORDER = "MISSING_BROKER_ORDER"
    DUPLICATE_BROKER_ORDER = "DUPLICATE_BROKER_ORDER"
    FILLED_QUANTITY_MISMATCH = "FILLED_QUANTITY_MISMATCH"
    STATUS_MISMATCH = "STATUS_MISMATCH"


@dataclass(frozen=True, slots=True)
class BrokerOrderSnapshot:
    broker_order_id: str
    status: OrderStatus
    quantity: Decimal
    filled_quantity: Decimal

    def __post_init__(self) -> None:
        if not self.broker_order_id.strip():
            raise ValueError("broker order ID cannot be empty")
        if self.quantity <= 0 or self.filled_quantity < 0 or self.filled_quantity > self.quantity:
            raise ValueError("invalid broker order quantities")


@dataclass(frozen=True, slots=True)
class ReconciliationIssue:
    issue_type: ReconciliationIssueType
    broker_order_id: str
    details: str


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    safe_to_trade: bool
    matched_orders: int
    issues: tuple[ReconciliationIssue, ...]


_PRE_BROKER_STATES = {
    OrderStatus.CREATED,
    OrderStatus.RISK_PENDING,
    OrderStatus.RISK_REJECTED,
    OrderStatus.APPROVED,
    OrderStatus.SUBMITTING,
}


def reconcile_orders(
    local_orders: tuple[OrderState, ...], broker_orders: tuple[BrokerOrderSnapshot, ...]
) -> ReconciliationResult:
    """Compare authoritative broker snapshots to local state; any ambiguity locks new trading."""
    issues: list[ReconciliationIssue] = []
    local_by_broker: dict[str, OrderState] = {}
    for order in local_orders:
        if order.broker_order_id is None:
            if order.status not in _PRE_BROKER_STATES:
                issues.append(
                    ReconciliationIssue(
                        ReconciliationIssueType.MISSING_BROKER_ORDER,
                        "<unassigned>",
                        f"local order {order.order_id} in {order.status.value} has no broker ID",
                    )
                )
            continue
        if order.broker_order_id in local_by_broker:
            issues.append(
                ReconciliationIssue(
                    ReconciliationIssueType.DUPLICATE_BROKER_ORDER,
                    order.broker_order_id,
                    "multiple local orders reference one broker order",
                )
            )
        else:
            local_by_broker[order.broker_order_id] = order

    broker_by_id: dict[str, BrokerOrderSnapshot] = {}
    for broker_order in broker_orders:
        if broker_order.broker_order_id in broker_by_id:
            issues.append(
                ReconciliationIssue(
                    ReconciliationIssueType.DUPLICATE_BROKER_ORDER,
                    broker_order.broker_order_id,
                    "broker returned duplicate order identity",
                )
            )
        else:
            broker_by_id[broker_order.broker_order_id] = broker_order

    matched = 0
    for broker_id, local in local_by_broker.items():
        broker = broker_by_id.get(broker_id)
        if broker is None:
            issues.append(
                ReconciliationIssue(
                    ReconciliationIssueType.MISSING_BROKER_ORDER,
                    broker_id,
                    f"local status is {local.status.value}",
                )
            )
            continue
        matched += 1
        if local.quantity != broker.quantity or local.filled_quantity != broker.filled_quantity:
            issues.append(
                ReconciliationIssue(
                    ReconciliationIssueType.FILLED_QUANTITY_MISMATCH,
                    broker_id,
                    f"local {local.filled_quantity}/{local.quantity}; "
                    f"broker {broker.filled_quantity}/{broker.quantity}",
                )
            )
        if local.status is not broker.status:
            issues.append(
                ReconciliationIssue(
                    ReconciliationIssueType.STATUS_MISMATCH,
                    broker_id,
                    f"local {local.status.value}; broker {broker.status.value}",
                )
            )

    for broker_id, broker in broker_by_id.items():
        if broker_id not in local_by_broker:
            issues.append(
                ReconciliationIssue(
                    ReconciliationIssueType.UNKNOWN_BROKER_ORDER,
                    broker_id,
                    f"broker status is {broker.status.value}",
                )
            )
    return ReconciliationResult(not issues, matched, tuple(issues))
