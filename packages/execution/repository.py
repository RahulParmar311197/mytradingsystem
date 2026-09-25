"""Persistent optimistic-concurrency repository for execution order state."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models import ExecutionOrderEventRecord, ExecutionOrderRecord
from packages.domain.models import OrderStatus
from packages.execution.state_machine import (
    OrderEvent,
    OrderEventType,
    OrderState,
    apply_order_event,
    initial_order_state,
)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class ExecutionOrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, order_id: UUID, quantity: Decimal, created_at: datetime) -> OrderState:
        state = initial_order_state(order_id, quantity, created_at)
        self.session.add(
            ExecutionOrderRecord(
                id=order_id,
                quantity=quantity,
                status=state.status.value,
                filled_quantity=state.filled_quantity,
                broker_order_id=None,
                last_event_at=state.last_event_at,
                version=0,
                reconciliation_reason=None,
            )
        )
        await self.session.flush()
        return state

    async def load(self, order_id: UUID) -> OrderState:
        record = await self.session.get(ExecutionOrderRecord, order_id)
        if record is None:
            raise LookupError(f"execution order {order_id} does not exist")
        event_ids = frozenset(
            (
                await self.session.scalars(
                    select(ExecutionOrderEventRecord.event_id).where(
                        ExecutionOrderEventRecord.order_id == order_id
                    )
                )
            ).all()
        )
        return OrderState(
            record.id,
            record.quantity,
            OrderStatus(record.status),
            record.filled_quantity,
            record.broker_order_id,
            _aware(record.last_event_at),
            event_ids,
            record.version,
            record.reconciliation_reason,
        )

    async def apply(self, order_id: UUID, event: OrderEvent) -> OrderState:
        current = await self.load(order_id)
        updated = apply_order_event(current, event)
        if updated is current:
            return current
        result = await self.session.execute(
            update(ExecutionOrderRecord)
            .where(
                ExecutionOrderRecord.id == order_id,
                ExecutionOrderRecord.version == current.version,
            )
            .values(
                status=updated.status.value,
                filled_quantity=updated.filled_quantity,
                broker_order_id=updated.broker_order_id,
                last_event_at=updated.last_event_at,
                version=updated.version,
                reconciliation_reason=updated.reconciliation_reason,
            )
        )
        if int(getattr(result, "rowcount", 0) or 0) != 1:
            raise RuntimeError("concurrent order update requires reload and reconciliation")
        self.session.add(
            ExecutionOrderEventRecord(
                order_id=order_id,
                event_id=event.event_id,
                event_type=event.event_type.value,
                occurred_at=event.occurred_at,
                fill_quantity=event.fill_quantity,
                broker_order_id=event.broker_order_id,
                resulting_version=updated.version,
            )
        )
        await self.session.flush()
        return updated

    async def events(self, order_id: UUID) -> tuple[OrderEvent, ...]:
        records = tuple(
            (
                await self.session.scalars(
                    select(ExecutionOrderEventRecord)
                    .where(ExecutionOrderEventRecord.order_id == order_id)
                    .order_by(ExecutionOrderEventRecord.resulting_version)
                )
            ).all()
        )
        return tuple(
            OrderEvent(
                record.event_id,
                OrderEventType(record.event_type),
                _aware(record.occurred_at),
                record.fill_quantity,
                record.broker_order_id,
            )
            for record in records
        )
