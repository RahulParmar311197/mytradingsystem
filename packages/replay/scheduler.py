"""Bounded server-side replay scheduling over durable coordinator steps."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from math import isfinite
from uuid import UUID

from packages.replay.persistence import StoredReplaySession
from packages.replay.service import ReplayCoordinator

AsyncCommit = Callable[[], Awaitable[None]]
AsyncSleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], datetime]
StopPredicate = Callable[[], bool]


class ReplayScheduleOutcome(StrEnum):
    COMPLETE = "complete"
    STOPPED = "stopped"
    STEP_LIMIT = "step_limit"


@dataclass(frozen=True, slots=True)
class ReplayScheduleResult:
    session: StoredReplaySession
    frames_emitted: int
    outcome: ReplayScheduleOutcome


class ReplayScheduler:
    """Advance one session serially, committing every emitted frame."""

    def __init__(
        self,
        coordinator: ReplayCoordinator,
        *,
        commit: AsyncCommit,
        sleep: AsyncSleep = asyncio.sleep,
        now: Clock = lambda: datetime.now(UTC),
    ) -> None:
        self.coordinator = coordinator
        self.commit = commit
        self.sleep = sleep
        self.now = now

    async def run(
        self,
        session_id: UUID,
        *,
        expected_version: int,
        candles_per_second: float = 1.0,
        maximum_steps: int = 1_000,
        should_stop: StopPredicate = lambda: False,
    ) -> ReplayScheduleResult:
        validate_schedule(candles_per_second, maximum_steps)

        stored, _ = await self.coordinator.snapshot(session_id)
        if stored.version != expected_version:
            raise ValueError("replay session version is stale")
        emitted = 0
        delay = 1 / candles_per_second

        while emitted < maximum_steps:
            if should_stop():
                return ReplayScheduleResult(stored, emitted, ReplayScheduleOutcome.STOPPED)
            if emitted:
                await self.sleep(delay)
                if should_stop():
                    return ReplayScheduleResult(stored, emitted, ReplayScheduleOutcome.STOPPED)
            mutation = await self.coordinator.step(
                session_id,
                expected_version=stored.version,
                checkpointed_at=self.now(),
            )
            if mutation.frame is None:
                return ReplayScheduleResult(stored, emitted, ReplayScheduleOutcome.COMPLETE)
            await self.commit()
            stored = mutation.session
            emitted += 1
            if stored.checkpoint.next_index == stored.total_events:
                return ReplayScheduleResult(stored, emitted, ReplayScheduleOutcome.COMPLETE)

        return ReplayScheduleResult(stored, emitted, ReplayScheduleOutcome.STEP_LIMIT)


def validate_schedule(candles_per_second: float, maximum_steps: int) -> None:
    if not isfinite(candles_per_second) or not 0.1 <= candles_per_second <= 100:
        raise ValueError("replay rate must be finite and between 0.1 and 100")
    if not 1 <= maximum_steps <= 10_000:
        raise ValueError("replay maximum steps must be between 1 and 10000")
