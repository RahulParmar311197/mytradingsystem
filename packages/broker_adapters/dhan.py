from decimal import Decimal
from typing import Any

import httpx

from packages.broker_adapters.base import (
    BrokerAPIError,
    BrokerOrderRequest,
    BrokerOrderResponse,
    validate_risk_approval,
)
from packages.domain.models import RiskDecision


def _number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


class DhanAdapter:
    """Dhan v2 order adapter. Mutating operations are deliberately never retried."""

    def __init__(self, client_id: str, access_token: str, client: httpx.AsyncClient) -> None:
        if not client_id.strip() or not access_token.strip():
            raise ValueError("Dhan client ID and access token are required")
        self._client_id = client_id
        self._client = client
        self._headers = {"access-token": access_token, "Accept": "application/json"}

    async def place_order(
        self, order: BrokerOrderRequest, risk_decision: RiskDecision
    ) -> BrokerOrderResponse:
        validate_risk_approval(order, risk_decision)
        try:
            exchange_segment, security_id = order.instrument_key.split(":", 1)
        except ValueError as error:
            raise ValueError("Dhan instrument key must be EXCHANGE_SEGMENT:SECURITY_ID") from error
        payload = {
            "dhanClientId": self._client_id,
            "correlationId": order.client_order_id,
            "transactionType": order.side.value,
            "exchangeSegment": exchange_segment,
            "productType": order.product,
            "orderType": order.order_type.value,
            "validity": order.validity,
            "securityId": security_id,
            "quantity": _number(order.quantity),
            "disclosedQuantity": _number(order.disclosed_quantity),
            "price": _number(order.price),
            "triggerPrice": _number(order.trigger_price),
            "afterMarketOrder": order.after_market,
        }
        response = await self._client.post(
            "https://api.dhan.co/v2/orders", headers=self._headers, json=payload
        )
        data = self._json(response, "place_order")
        order_id = str(data.get("orderId", ""))
        if not order_id:
            raise BrokerAPIError("place_order_invalid_response", response.status_code)
        return BrokerOrderResponse(order_id, str(data.get("orderStatus", "")))

    async def get_order(self, broker_order_id: str) -> BrokerOrderResponse:
        response = await self._client.get(
            f"https://api.dhan.co/v2/orders/{broker_order_id}", headers=self._headers
        )
        data = self._json(response, "get_order")
        return BrokerOrderResponse(
            str(data.get("orderId", broker_order_id)), str(data.get("orderStatus", ""))
        )

    async def cancel_order(self, broker_order_id: str) -> BrokerOrderResponse:
        response = await self._client.delete(
            f"https://api.dhan.co/v2/orders/{broker_order_id}", headers=self._headers
        )
        data = self._json(response, "cancel_order")
        return BrokerOrderResponse(
            str(data.get("orderId", broker_order_id)), str(data.get("orderStatus", ""))
        )

    @staticmethod
    def _json(response: httpx.Response, operation: str) -> dict[str, Any]:
        if not response.is_success:
            raise BrokerAPIError(operation, response.status_code)
        value = response.json()
        if not isinstance(value, dict):
            raise BrokerAPIError(f"{operation}_invalid_response", response.status_code)
        return value
