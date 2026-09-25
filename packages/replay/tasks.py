"""Single-process ownership for bounded replay scheduler tasks."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from packages.replay.scheduler import ReplayScheduleResult, validate_schedule

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ReplayTaskRequest:
    session_id: UUID
    expected_version: int
    candles_per_second: float
    maximum_steps: int
    task_id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if self.expected_version < 0:
            raise ValueError("replay expected version must be non-negative")
        validate_schedule(self.candles_per_second, self.maximum_steps)


class ReplayTaskOutcome(StrEnum):
    RUNNING = "running"
    COMPLETE = "complete"
    STOPPED = "stopped"
    STEP_LIMIT = "step_limit"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ReplayTaskStatus:
    request: ReplayTaskRequest
    outcome: ReplayTaskOutcome
    frames_emitted: int
    resulting_version: int | None
    started_at: datetime
    finished_at: datetime | None


ReplayTaskRunner = Callable[[ReplayTaskRequest, asyncio.Event], Awaitable[ReplayScheduleResult]]
ReplayTaskStatusObserver = Callable[[ReplayTaskStatus], Awaitable[None]]
Clock = Callable[[], datetime]


@dataclass(slots=True)
class _OwnedTask:
    status: ReplayTaskStatus
    stop: asyncio.Event
    task: asyncio.Task[None]


class ReplayTaskManager:
    """Own at most one in-process scheduler task for each replay session."""

    def __init__(
        self,
        runner: ReplayTaskRunner,
        *,
        status_observer: ReplayTaskStatusObserver | None = None,
        now: Clock = lambda: datetime.now(UTC),
    ) -> None:
        self.runner = runner
        self.status_observer = status_observer
        self.now = now
        self._lock = asyncio.Lock()
        self._tasks: dict[UUID, _OwnedTask] = {}

    async def start(self, request: ReplayTaskRequest) -> ReplayTaskStatus:
        async with self._lock:
            existing = self._tasks.get(request.session_id)
            if existing is not None and not existing.task.done():
                raise ValueError("replay session already has a running scheduler task")
            started = self.now()
            status = ReplayTaskStatus(request, ReplayTaskOutcome.RUNNING, 0, None, started, None)
            if self.status_observer is not None:
                await self.status_observer(status)
            stop = asyncio.Event()
            task = asyncio.create_task(
                self._execute(request, stop), name=f"replay:{request.session_id}"
            )
            self._tasks[request.session_id] = _OwnedTask(status, stop, task)
            return status

    async def status(self, session_id: UUID) -> ReplayTaskStatus:
        async with self._lock:
            owned = self._tasks.get(session_id)
            if owned is None:
                raise KeyError("replay scheduler task does not exist")
            return owned.status

    async def stop(self, session_id: UUID) -> ReplayTaskStatus:
        async with self._lock:
            owned = self._tasks.get(session_id)
            if owned is None:
                raise KeyError("replay scheduler task does not exist")
            owned.stop.set()
            task = owned.task
        await task
        return await self.status(session_id)

    async def close(self) -> None:
        async with self._lock:
            owned_tasks = tuple(self._tasks.values())
            for owned in owned_tasks:
                owned.stop.set()
        await asyncio.gather(*(owned.task for owned in owned_tasks), return_exceptions=True)

    async def _execute(self, request: ReplayTaskRequest, stop: asyncio.Event) -> None:
        try:
            result = await self.runner(request, stop)
            outcome = ReplayTaskOutcome(result.outcome.value)
            status = ReplayTaskStatus(
                request,
                outcome,
                result.frames_emitted,
                result.session.version,
                (await self.status(request.session_id)).started_at,
                self.now(),
            )
        except Exception:
            logger.exception("replay_scheduler_task_failed session_id=%s", request.session_id)
            current = await self.status(request.session_id)
            status = ReplayTaskStatus(
                request,
                ReplayTaskOutcome.FAILED,
                current.frames_emitted,
                current.resulting_version,
                current.started_at,
                self.now(),
            )
        async with self._lock:
            owned = self._tasks.get(request.session_id)
            if owned is not None:
                owned.status = status
        if self.status_observer is not None:
            try:
                await self.status_observer(status)
            except Exception:
                logger.exception(
                    "replay_scheduler_status_persistence_failed task_id=%s", request.task_id
                )
