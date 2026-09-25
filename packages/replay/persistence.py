"""Restart-safe replay checkpoint persistence with optimistic concurrency."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models import ReplaySessionRecord
from packages.replay.engine import ReplayCheckpoint, ReplayEngine


@dataclass(frozen=True, slots=True)
class StoredReplaySession:
    session_id: UUID
    checkpoint: ReplayCheckpoint
    instrument_id: UUID
    timeframe_seconds: int
    total_events: int
    version: int
    checkpointed_at: datetime


class ReplaySessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self, session_id: UUID, engine: ReplayEngine, *, checkpointed_at: datetime
    ) -> StoredReplaySession:
        checkpointed_at = _utc(checkpointed_at)
        existing = await self.session.get(ReplaySessionRecord, session_id)
        if existing is not None:
            stored = _stored(existing)
            if (
                stored.checkpoint.dataset_sha256 != engine.dataset_sha256
                or stored.instrument_id != engine.instrument_id
                or stored.timeframe_seconds != engine.timeframe_seconds
                or stored.total_events != engine.total
            ):
                raise ValueError("replay session ID has conflicting dataset evidence")
            return stored
        checkpoint = engine.checkpoint()
        record = ReplaySessionRecord(
            id=session_id,
            dataset_sha256=checkpoint.dataset_sha256,
            instrument_id=engine.instrument_id,
            timeframe_seconds=engine.timeframe_seconds,
            next_index=checkpoint.next_index,
            total_events=engine.total,
            version=0,
            checkpointed_at=checkpointed_at,
        )
        self.session.add(record)
        await self.session.flush()
        return _stored(record)

    async def load(self, session_id: UUID) -> StoredReplaySession:
        record = await self.session.get(ReplaySessionRecord, session_id)
        if record is None:
            raise KeyError("replay session does not exist")
        return _stored(record)

    async def list_recent(
        self, *, limit: int = 25, offset: int = 0
    ) -> tuple[StoredReplaySession, ...]:
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("replay page requires limit 1..100 and non-negative offset")
        records = (
            await self.session.scalars(
                select(ReplaySessionRecord)
                .order_by(
                    ReplaySessionRecord.checkpointed_at.desc(),
                    ReplaySessionRecord.id.asc(),
                )
                .offset(offset)
                .limit(limit)
            )
        ).all()
        return tuple(_stored(record) for record in records)

    async def save(
        self,
        session_id: UUID,
        checkpoint: ReplayCheckpoint,
        *,
        expected_version: int,
        checkpointed_at: datetime,
    ) -> StoredReplaySession:
        checkpointed_at = _utc(checkpointed_at)
        if expected_version < 0 or checkpoint.next_index < 0:
            raise ValueError("replay checkpoint version and index must be non-negative")
        result = cast(
            CursorResult[Any],
            await self.session.execute(
                update(ReplaySessionRecord)
                .where(
                    ReplaySessionRecord.id == session_id,
                    ReplaySessionRecord.version == expected_version,
                    ReplaySessionRecord.dataset_sha256 == checkpoint.dataset_sha256,
                    ReplaySessionRecord.total_events >= checkpoint.next_index,
                )
                .values(
                    next_index=checkpoint.next_index,
                    version=expected_version + 1,
                    checkpointed_at=checkpointed_at,
                )
            ),
        )
        if result.rowcount != 1:
            raise ValueError("replay checkpoint is stale, mismatched, or out of range")
        return await self.load(session_id)


def _stored(record: ReplaySessionRecord) -> StoredReplaySession:
    timestamp = record.checkpointed_at
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    else:
        timestamp = timestamp.astimezone(UTC)
    return StoredReplaySession(
        record.id,
        ReplayCheckpoint(record.dataset_sha256, record.next_index),
        record.instrument_id,
        record.timeframe_seconds,
        record.total_events,
        record.version,
        timestamp,
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("replay checkpoint timestamp must be timezone-aware")
    return value.astimezone(UTC)
