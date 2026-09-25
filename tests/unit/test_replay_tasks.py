import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from packages.replay import (
    ReplayCheckpoint,
    ReplayScheduleOutcome,
    ReplayScheduleResult,
    ReplayTaskManager,
    ReplayTaskOutcome,
    ReplayTaskRequest,
    StoredReplaySession,
)

NOW = datetime(2026, 9, 24, 11, tzinfo=UTC)


def result(request: ReplayTaskRequest, outcome: ReplayScheduleOutcome) -> ReplayScheduleResult:
    stored = StoredReplaySession(
        request.session_id,
        ReplayCheckpoint("a" * 64, 2),
        uuid4(),
        60,
        3,
        request.expected_version + 2,
        NOW,
    )
    return ReplayScheduleResult(stored, 2, outcome)


@pytest.mark.asyncio
async def test_task_manager_owns_one_task_and_records_completion() -> None:
    release = asyncio.Event()

    async def runner(request: ReplayTaskRequest, stop: asyncio.Event) -> ReplayScheduleResult:
        await release.wait()
        return result(request, ReplayScheduleOutcome.COMPLETE)

    request = ReplayTaskRequest(uuid4(), 4, 2, 10)
    manager = ReplayTaskManager(runner, now=lambda: NOW)
    started = await manager.start(request)
    assert started.outcome is ReplayTaskOutcome.RUNNING
    with pytest.raises(ValueError, match="already has"):
        await manager.start(request)
    release.set()
    completed = await manager.stop(request.session_id)
    assert completed.outcome is ReplayTaskOutcome.COMPLETE
    assert completed.frames_emitted == 2
    assert completed.resulting_version == 6
    assert completed.finished_at == NOW
    await manager.close()


@pytest.mark.asyncio
async def test_task_manager_stops_and_closes_owned_tasks() -> None:
    async def runner(request: ReplayTaskRequest, stop: asyncio.Event) -> ReplayScheduleResult:
        await stop.wait()
        return result(request, ReplayScheduleOutcome.STOPPED)

    first = ReplayTaskRequest(uuid4(), 0, 1, 10)
    second = ReplayTaskRequest(uuid4(), 0, 1, 10)
    manager = ReplayTaskManager(runner, now=lambda: NOW + timedelta(seconds=1))
    await manager.start(first)
    await manager.start(second)
    stopped = await manager.stop(first.session_id)
    assert stopped.outcome is ReplayTaskOutcome.STOPPED
    await manager.close()
    assert (await manager.status(second.session_id)).outcome is ReplayTaskOutcome.STOPPED
    with pytest.raises(KeyError, match="does not exist"):
        await manager.status(uuid4())


@pytest.mark.asyncio
async def test_task_manager_records_runner_failure_without_raising_from_stop() -> None:
    async def runner(request: ReplayTaskRequest, stop: asyncio.Event) -> ReplayScheduleResult:
        raise RuntimeError("sensitive failure detail")

    request = ReplayTaskRequest(uuid4(), 0, 1, 10)
    manager = ReplayTaskManager(runner, now=lambda: NOW)
    await manager.start(request)
    failed = await manager.stop(request.session_id)
    assert failed.outcome is ReplayTaskOutcome.FAILED
    assert failed.frames_emitted == 0
    assert failed.resulting_version is None
    assert failed.finished_at == NOW


def test_task_request_rejects_invalid_bounds() -> None:
    with pytest.raises(ValueError, match="expected version"):
        ReplayTaskRequest(uuid4(), -1, 1, 1)
    with pytest.raises(ValueError, match="rate"):
        ReplayTaskRequest(uuid4(), 0, float("nan"), 1)
