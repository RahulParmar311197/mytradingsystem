import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest

from packages.broker_adapters import (
    BrokerAPIError,
    BrokerOrderRequest,
    DhanAdapter,
    UpstoxAdapter,
)
from packages.domain.models import OrderType, RiskDecision, RiskOutcome, Side

UPSTOX_INSTRUMENT = "NSE_EQ|INE123"


def order(instrument_key: str) -> BrokerOrderRequest:
    return BrokerOrderRequest(
        order_intent_id=uuid4(),
        client_order_id="client-order-123",
        instrument_key=instrument_key,
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal(25),
        product="I",
        price=Decimal("100.5"),
        disclosed_quantity=Decimal(5),
    )


def approval(request: BrokerOrderRequest) -> RiskDecision:
    return RiskDecision(
        order_intent_id=request.order_intent_id,
        timestamp=datetime(2026, 9, 19, tzinfo=UTC),
        outcome=RiskOutcome.APPROVED,
        approved_quantity=request.quantity,
        reason_codes=("APPROVED",),
        risk_policy_version="contract-v1",
    )


@pytest.mark.asyncio
async def test_upstox_order_contract_and_auth_header() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"status": "success", "data": {"order_id": "UP-1"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        request_order = order(UPSTOX_INSTRUMENT)
        result = await UpstoxAdapter("upstox-secret", client).place_order(
            request_order, approval(request_order)
        )
    assert result.broker_order_id == "UP-1"
    request = captured[0]
    assert str(request.url) == "https://api-hft.upstox.com/v2/order/place"
    assert request.headers["authorization"] == "Bearer upstox-secret"
    payload = json.loads(request.content)
    assert payload["tag"] == "client-order-123"
    assert payload["instrument_token"] == UPSTOX_INSTRUMENT
    assert payload["transaction_type"] == "BUY"
    assert payload["order_type"] == "LIMIT"
    assert payload["quantity"] == 25


@pytest.mark.asyncio
async def test_dhan_order_contract_and_auth_headers() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"orderId": "DH-1", "orderStatus": "PENDING"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        request_order = order("NSE_FNO:12345")
        result = await DhanAdapter("dhan-client", "dhan-secret", client).place_order(
            request_order, approval(request_order)
        )
    assert result.broker_order_id == "DH-1"
    request = captured[0]
    assert str(request.url) == "https://api.dhan.co/v2/orders"
    assert request.headers["access-token"] == "dhan-secret"
    payload = json.loads(request.content)
    assert payload["dhanClientId"] == "dhan-client"
    assert payload["correlationId"] == "client-order-123"
    assert payload["exchangeSegment"] == "NSE_FNO"
    assert payload["securityId"] == "12345"
    assert payload["quantity"] == 25


@pytest.mark.asyncio
@pytest.mark.parametrize("broker", ["upstox", "dhan"])
async def test_order_placement_failure_is_not_retried(broker: str) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, json={"error": "unavailable"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = (
            UpstoxAdapter("secret", client)
            if broker == "upstox"
            else DhanAdapter("client", "secret", client)
        )
        with pytest.raises(BrokerAPIError, match="HTTP 503"):
            request_order = order(UPSTOX_INSTRUMENT if broker == "upstox" else "NSE_EQ:1")
            await adapter.place_order(request_order, approval(request_order))
    assert attempts == 1


@pytest.mark.asyncio
async def test_adapter_rejects_order_without_matching_risk_before_network() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(200, json={})

    request_order = order(UPSTOX_INSTRUMENT)
    wrong = approval(request_order).model_copy(update={"order_intent_id": uuid4()})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(PermissionError, match="does not belong"):
            await UpstoxAdapter("secret", client).place_order(request_order, wrong)
    assert attempts == 0
