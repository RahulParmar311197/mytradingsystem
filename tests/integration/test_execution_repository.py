from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database.base import Base
from packages.database.models import ExecutionOrderEventRecord
from packages.domain.models import OrderStatus
from packages.execution import ExecutionOrderRepository, OrderEvent, OrderEventType


@pytest.mark.asyncio
async def test_execution_state_and_events_recover_after_restart() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    order_id = uuid4()
    now = datetime(2026, 9, 19, 5, tzinfo=UTC)
    lifecycle = (
        OrderEvent("risk-pending", OrderEventType.RISK_REQUESTED, now + timedelta(seconds=1)),
        OrderEvent("risk-approved", OrderEventType.RISK_APPROVED, now + timedelta(seconds=2)),
        OrderEvent("submitting", OrderEventType.SUBMIT_STARTED, now + timedelta(seconds=3)),
        OrderEvent(
            "submitted",
            OrderEventType.SUBMIT_CONFIRMED,
            now + timedelta(seconds=4),
            broker_order_id="broker-1",
        ),
        OrderEvent("fill-1", OrderEventType.FILL, now + timedelta(seconds=5), Decimal(4)),
    )
    async with sessions() as session:
        repository = ExecutionOrderRepository(session)
        await repository.create(order_id, Decimal(10), now)
        for event in lifecycle:
            await repository.apply(order_id, event)
        await session.commit()
    async with sessions() as session:
        repository = ExecutionOrderRepository(session)
        recovered = await repository.load(order_id)
        assert recovered.status is OrderStatus.PARTIALLY_FILLED
        assert recovered.filled_quantity == 4
        assert recovered.version == 5
        assert recovered.broker_order_id == "broker-1"
        assert await repository.events(order_id) == lifecycle
        duplicate = await repository.apply(order_id, lifecycle[-1])
        assert duplicate == recovered
        assert (
            await session.scalar(select(func.count()).select_from(ExecutionOrderEventRecord)) == 5
        )
    await engine.dispose()


@pytest.mark.asyncio
async def test_reconciliation_state_is_persisted_with_reason() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    order_id = uuid4()
    now = datetime(2026, 9, 19, 5, tzinfo=UTC)
    async with sessions() as session:
        repository = ExecutionOrderRepository(session)
        await repository.create(order_id, Decimal(1), now)
        await repository.apply(
            order_id, OrderEvent("risk", OrderEventType.RISK_REQUESTED, now + timedelta(seconds=1))
        )
        await repository.apply(
            order_id,
            OrderEvent("approved", OrderEventType.RISK_APPROVED, now + timedelta(seconds=2)),
        )
        await repository.apply(
            order_id,
            OrderEvent("submit", OrderEventType.SUBMIT_STARTED, now + timedelta(seconds=3)),
        )
        state = await repository.apply(
            order_id,
            OrderEvent("unknown", OrderEventType.SUBMISSION_UNKNOWN, now + timedelta(seconds=4)),
        )
        await session.commit()
        assert state.status is OrderStatus.RECONCILIATION_REQUIRED
        assert state.reconciliation_reason == "SUBMISSION_OUTCOME_UNKNOWN"
    async with sessions() as session:
        recovered = await ExecutionOrderRepository(session).load(order_id)
        assert recovered.status is OrderStatus.RECONCILIATION_REQUIRED
        assert recovered.reconciliation_reason == "SUBMISSION_OUTCOME_UNKNOWN"
    await engine.dispose()
