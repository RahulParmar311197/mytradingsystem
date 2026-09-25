from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from packages.domain.models import OrderType, RiskDecision, RiskOutcome, Side


@dataclass(frozen=True, slots=True)
class BrokerOrderRequest:
    order_intent_id: UUID
    client_order_id: str
    instrument_key: str
    side: Side
    order_type: OrderType
    quantity: Decimal
    product: str
    validity: str = "DAY"
    price: Decimal = Decimal(0)
    trigger_price: Decimal = Decimal(0)
    disclosed_quantity: Decimal = Decimal(0)
    after_market: bool = False

    def __post_init__(self) -> None:
        if not self.client_order_id.strip() or not self.instrument_key.strip():
            raise ValueError("client order ID and instrument key are required")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if min(self.price, self.trigger_price, self.disclosed_quantity) < 0:
            raise ValueError("order prices and disclosed quantity cannot be negative")
        if self.disclosed_quantity > self.quantity:
            raise ValueError("disclosed quantity cannot exceed quantity")


@dataclass(frozen=True, slots=True)
class BrokerOrderResponse:
    broker_order_id: str
    status: str


class BrokerAPIError(RuntimeError):
    def __init__(self, operation: str, status_code: int) -> None:
        self.operation = operation
        self.status_code = status_code
        super().__init__(f"broker {operation} failed with HTTP {status_code}")


class BrokerAdapter(Protocol):
    async def place_order(
        self, order: BrokerOrderRequest, risk_decision: RiskDecision
    ) -> BrokerOrderResponse: ...

    async def get_order(self, broker_order_id: str) -> BrokerOrderResponse: ...

    async def cancel_order(self, broker_order_id: str) -> BrokerOrderResponse: ...


def validate_risk_approval(order: BrokerOrderRequest, risk: RiskDecision) -> None:
    if risk.order_intent_id != order.order_intent_id:
        raise PermissionError("risk decision does not belong to broker order request")
    if risk.outcome not in (RiskOutcome.APPROVED, RiskOutcome.RESIZED):
        raise PermissionError("approved independent risk decision is required")
    if risk.approved_quantity != order.quantity:
        raise PermissionError("broker quantity must equal independently approved quantity")


ExecutionAuthorizer = Callable[[BrokerOrderRequest, RiskDecision], None]


def authorize_dispatch(
    order: BrokerOrderRequest,
    risk: RiskDecision,
    authorizer: ExecutionAuthorizer | None,
) -> None:
    """The broker boundary stays closed until a persistent execution policy is wired."""
    validate_risk_approval(order, risk)
    if authorizer is None:
        raise PermissionError("broker order dispatch requires an execution authorizer")
    authorizer(order, risk)
