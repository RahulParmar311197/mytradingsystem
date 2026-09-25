from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database import Base
from packages.database.models import ReplaySessionRecord
from packages.replay import (
    ReplayTaskOutcome,
    ReplayTaskRequest,
    ReplayTaskStatus,
    ReplayTaskStatusRepository,
)

NOW = datetime(2026, 9, 24, 12, tzinfo=UTC)


@pytest.mark.asyncio
async def test_replay_task_status_is_persisted_and_terminal_once(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'replay-runs.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    session_id = uuid4()
    request = ReplayTaskRequest(session_id, 2, 5, 10)
    running = ReplayTaskStatus(request, ReplayTaskOutcome.RUNNING, 0, None, NOW, None)
    complete = ReplayTaskStatus(
        request, ReplayTaskOutcome.COMPLETE, 3, 5, NOW, NOW + timedelta(seconds=1)
    )

    async with sessions() as session:
        session.add(
            ReplaySessionRecord(
                id=session_id,
                dataset_sha256="a" * 64,
                instrument_id=uuid4(),
                timeframe_seconds=60,
                next_index=2,
                total_events=10,
                version=2,
                checkpointed_at=NOW,
            )
        )
        await session.flush()
        repository = ReplayTaskStatusRepository(session)
        await repository.record(running)
        await repository.record(complete)
        await session.commit()

    async with sessions() as session:
        repository = ReplayTaskStatusRepository(session)
        stored = (await repository.list_for_session(session_id))[0]
        assert stored == complete
        assert await repository.latest_for_session(session_id) == complete
        assert await repository.load(request.task_id) == complete
        with pytest.raises(KeyError, match="does not exist"):
            await repository.latest_for_session(uuid4())
        with pytest.raises(KeyError, match="does not exist"):
            await repository.load(uuid4())
        with pytest.raises(ValueError, match="already terminal"):
            await repository.record(complete)
        with pytest.raises(ValueError, match="task ID already exists"):
            await repository.record(running)

    await engine.dispose()
