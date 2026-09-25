"""Durable replay playback-run evidence."""

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models import ReplayPlaybackRunRecord
from packages.replay.tasks import ReplayTaskOutcome, ReplayTaskRequest, ReplayTaskStatus


class ReplayTaskStatusRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(self, status: ReplayTaskStatus) -> ReplayTaskStatus:
        if status.outcome is ReplayTaskOutcome.RUNNING:
            if await self.session.get(ReplayPlaybackRunRecord, status.request.task_id) is not None:
                raise ValueError("replay playback task ID already exists")
            self.session.add(
                ReplayPlaybackRunRecord(
                    id=status.request.task_id,
                    session_id=status.request.session_id,
                    expected_version=status.request.expected_version,
                    candles_per_second=status.request.candles_per_second,
                    maximum_steps=status.request.maximum_steps,
                    outcome=status.outcome.value,
                    frames_emitted=0,
                    resulting_version=None,
                    started_at=_utc(status.started_at),
                    finished_at=None,
                )
            )
            await self.session.flush()
            return status

        result = cast(
            CursorResult[Any],
            await self.session.execute(
                update(ReplayPlaybackRunRecord)
                .where(
                    ReplayPlaybackRunRecord.id == status.request.task_id,
                    ReplayPlaybackRunRecord.session_id == status.request.session_id,
                    ReplayPlaybackRunRecord.outcome == ReplayTaskOutcome.RUNNING.value,
                )
                .values(
                    outcome=status.outcome.value,
                    frames_emitted=status.frames_emitted,
                    resulting_version=status.resulting_version,
                    finished_at=_utc_required(status.finished_at),
                )
            ),
        )
        if result.rowcount != 1:
            raise ValueError("replay playback task is missing or already terminal")
        return status

    async def list_for_session(
        self, session_id: UUID, *, limit: int = 25, offset: int = 0
    ) -> tuple[ReplayTaskStatus, ...]:
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("replay playback page requires limit 1..100 and non-negative offset")
        records = (
            await self.session.scalars(
                select(ReplayPlaybackRunRecord)
                .where(ReplayPlaybackRunRecord.session_id == session_id)
                .order_by(
                    ReplayPlaybackRunRecord.started_at.desc(),
                    ReplayPlaybackRunRecord.id.asc(),
                )
                .offset(offset)
                .limit(limit)
            )
        ).all()
        return tuple(_status(record) for record in records)

    async def latest_for_session(self, session_id: UUID) -> ReplayTaskStatus:
        record = await self.session.scalar(
            select(ReplayPlaybackRunRecord)
            .where(ReplayPlaybackRunRecord.session_id == session_id)
            .order_by(
                ReplayPlaybackRunRecord.started_at.desc(),
                ReplayPlaybackRunRecord.id.asc(),
            )
            .limit(1)
        )
        if record is None:
            raise KeyError("replay playback task does not exist")
        return _status(record)

    async def load(self, task_id: UUID) -> ReplayTaskStatus:
        record = await self.session.get(ReplayPlaybackRunRecord, task_id)
        if record is None:
            raise KeyError("replay playback task does not exist")
        return _status(record)


def _status(record: ReplayPlaybackRunRecord) -> ReplayTaskStatus:
    request = ReplayTaskRequest(
        record.session_id,
        record.expected_version,
        record.candles_per_second,
        record.maximum_steps,
        record.id,
    )
    return ReplayTaskStatus(
        request,
        ReplayTaskOutcome(record.outcome),
        record.frames_emitted,
        record.resulting_version,
        _utc(record.started_at),
        None if record.finished_at is None else _utc(record.finished_at),
    )


def _utc_required(value: datetime | None) -> datetime:
    if value is None:
        raise ValueError("terminal replay playback status requires a finished timestamp")
    return _utc(value)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
