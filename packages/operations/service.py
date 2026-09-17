from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models import AuditEventRecord, SafetyStateRecord, ServiceHeartbeatRecord
from packages.domain.models import DomainModel
from packages.observability.logging import safe_context


class SafetyState(DomainModel):
    entries_locked: bool
    reason: str
    updated_at: datetime | None


async def read_safety(session: AsyncSession) -> SafetyState:
    state = await session.get(SafetyStateRecord, "kill_switch", populate_existing=True)
    if state is None:
        return SafetyState(entries_locked=True, reason="SAFETY_STATE_MISSING", updated_at=None)
    timestamp = state.updated_at
    if timestamp.tzinfo is None and session.get_bind().dialect.name == "sqlite":
        timestamp = timestamp.replace(tzinfo=UTC)
    return SafetyState(entries_locked=state.enabled, reason=state.reason, updated_at=timestamp)


def audit(
    session: AsyncSession,
    *,
    actor: str,
    action: str,
    resource: str,
    correlation_id: str,
    outcome: str,
    details: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditEventRecord(
            occurred_at=datetime.now(UTC),
            actor_id=actor,
            action=action,
            resource_type=resource,
            outcome=outcome,
            correlation_id=correlation_id,
            details=safe_context(details or {}),
        )
    )


async def set_kill_switch(
    session: AsyncSession,
    *,
    enabled: bool,
    reason: str,
    actor: str,
    correlation_id: str,
) -> SafetyState:
    if not reason.strip() or len(reason) > 256:
        raise ValueError("a reason of 1-256 characters is required")
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert  # type: ignore[assignment]
    else:
        raise ValueError("unsupported database")
    values = dict(
        key="kill_switch",
        enabled=enabled,
        reason=reason,
        updated_at=datetime.now(UTC),
        correlation_id=correlation_id,
    )
    await session.execute(
        insert(SafetyStateRecord)
        .values(**values)
        .on_conflict_do_update(
            index_elements=["key"],
            set_=values,
        )
    )
    audit(
        session,
        actor=actor,
        action="kill_switch.changed",
        resource="safety_state",
        correlation_id=correlation_id,
        outcome="locked" if enabled else "unlocked",
        details={"reason": reason},
    )
    await session.flush()
    return await read_safety(session)


async def record_heartbeat(
    session: AsyncSession, *, healthy: bool, checks: dict[str, bool]
) -> None:
    now = datetime.now(UTC)
    row = await session.get(ServiceHeartbeatRecord, "worker")
    if row is None:
        session.add(
            ServiceHeartbeatRecord(
                service="worker", observed_at=now, healthy=healthy, details=checks
            )
        )
    else:
        row.observed_at, row.healthy, row.details = now, healthy, checks
    # Heartbeats are operational observations, not trading authorization.
    if not healthy:
        await set_kill_switch(
            session,
            enabled=True,
            reason="Worker dependency check failed",
            actor="worker",
            correlation_id=str(uuid4()),
        )
