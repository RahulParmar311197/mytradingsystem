from decimal import Decimal
from typing import Any

import httpx

from packages.broker_adapters.base import (
    BrokerAPIError,
    BrokerOrderRequest,
    BrokerOrderResponse,
    ExecutionAuthorizer,
    authorize_dispatch,
)
from packages.domain.models import RiskDecision


def _number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


class UpstoxAdapter:
    """Upstox v2 order adapter. Mutating operations are deliberately never retried."""

    def __init__(
        self,
        access_token: str,
        client: httpx.AsyncClient,
        *,
        execution_authorizer: ExecutionAuthorizer | None = None,
    ) -> None:
        if not access_token.strip():
            raise ValueError("Upstox access token is required")
        self._client = client
        self._execution_authorizer = execution_authorizer
        self._headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}

    async def place_order(
        self, order: BrokerOrderRequest, risk_decision: RiskDecision
    ) -> BrokerOrderResponse:
        authorize_dispatch(order, risk_decision, self._execution_authorizer)
        payload = {
            "quantity": _number(order.quantity),
            "product": order.product,
            "validity": order.validity,
            "price": _number(order.price),
            "tag": order.client_order_id,
            "instrument_token": order.instrument_key,
            "order_type": order.order_type.value,
            "transaction_type": order.side.value,
            "disclosed_quantity": _number(order.disclosed_quantity),
            "trigger_price": _number(order.trigger_price),
            "is_amo": order.after_market,
        }
        response = await self._client.post(
            "https://api-hft.upstox.com/v2/order/place", headers=self._headers, json=payload
        )
        data = self._json(response, "place_order")
        order_id = str(data.get("data", {}).get("order_id", ""))
        if not order_id:
            raise BrokerAPIError("place_order_invalid_response", response.status_code)
        return BrokerOrderResponse(order_id, str(data.get("status", "success")))

    async def get_order(self, broker_order_id: str) -> BrokerOrderResponse:
        response = await self._client.get(
            "https://api.upstox.com/v2/order/details",
            headers=self._headers,
            params={"order_id": broker_order_id},
        )
        data = self._json(response, "get_order")
        details = data.get("data", {})
        return BrokerOrderResponse(
            str(details.get("order_id", broker_order_id)), str(details.get("status", ""))
        )

    async def cancel_order(self, broker_order_id: str) -> BrokerOrderResponse:
        response = await self._client.delete(
            "https://api-hft.upstox.com/v2/order/cancel",
            headers=self._headers,
            params={"order_id": broker_order_id},
        )
        data = self._json(response, "cancel_order")
        order_id = str(data.get("data", {}).get("order_id", broker_order_id))
        return BrokerOrderResponse(order_id, str(data.get("status", "success")))

    @staticmethod
    def _json(response: httpx.Response, operation: str) -> dict[str, Any]:
        if not response.is_success:
            raise BrokerAPIError(operation, response.status_code)
        value = response.json()
        if not isinstance(value, dict):
            raise BrokerAPIError(f"{operation}_invalid_response", response.status_code)
        return value
