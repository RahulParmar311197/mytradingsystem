"""Authenticated replay HTTP routes separated from application bootstrap."""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from packages.auth import Principal
from packages.database import Database
from packages.domain.models import Candle
from packages.replay import (
    ReplayCoordinator,
    ReplayDatasetRepository,
    ReplayEngine,
    ReplaySessionRepository,
    ReplayTaskManager,
    ReplayTaskOutcome,
    ReplayTaskRequest,
    ReplayTaskStatus,
    ReplayTaskStatusRepository,
    StoredReplayDataset,
    StoredReplaySession,
)

logger = logging.getLogger(__name__)
PrincipalDependency = Callable[..., Principal | Awaitable[Principal]]


class ReplayDatasetRequest(BaseModel):
    candles: tuple[Candle, ...] = Field(min_length=1, max_length=10_000)


class ReplaySessionRequest(BaseModel):
    session_id: UUID = Field(default_factory=uuid4)
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReplayVersionRequest(BaseModel):
    expected_version: int = Field(ge=0)


class ReplaySeekRequest(ReplayVersionRequest):
    as_of: AwareDatetime


class ReplayPlaybackRequest(ReplayVersionRequest):
    candles_per_second: float = Field(default=1, ge=0.1, le=100)
    maximum_steps: int = Field(default=1_000, ge=1, le=10_000)


def create_replay_router(
    database: Database,
    *,
    task_manager: ReplayTaskManager,
    authenticated_principal: PrincipalDependency,
    operator_principal: PrincipalDependency,
) -> APIRouter:
    """Build replay routes with app-scoped database and authorization dependencies."""
    router = APIRouter(tags=["replay"])

    @router.post(
        "/api/v1/operator/replay/datasets",
        status_code=status.HTTP_201_CREATED,
    )
    async def create_replay_dataset(
        payload: ReplayDatasetRequest,
        _: Annotated[Principal, Depends(operator_principal)],
    ) -> dict[str, object]:
        try:
            async with database.sessions() as session:
                stored = await ReplayDatasetRepository(session).store(
                    payload.candles, created_at=datetime.now(UTC)
                )
                await session.commit()
        except ValueError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        except Exception as error:
            logger.error("replay_dataset_write_failed")
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "replay dataset storage is unavailable"
            ) from error
        return _dataset_payload(stored)

    @router.post(
        "/api/v1/operator/replay/sessions",
        status_code=status.HTTP_201_CREATED,
    )
    async def create_replay_session(
        payload: ReplaySessionRequest,
        _: Annotated[Principal, Depends(operator_principal)],
    ) -> dict[str, object]:
        try:
            async with database.sessions() as session:
                candles = await ReplayDatasetRepository(session).load(payload.dataset_sha256)
                stored = await ReplaySessionRepository(session).create(
                    payload.session_id,
                    ReplayEngine(candles),
                    checkpointed_at=datetime.now(UTC),
                )
                await session.commit()
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        except ValueError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        except Exception as error:
            logger.error("replay_session_write_failed")
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "replay session storage is unavailable"
            ) from error
        return _session_payload(stored)

    @router.get("/api/v1/replay/datasets")
    async def list_replay_datasets(
        _: Annotated[Principal, Depends(authenticated_principal)],
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, object]:
        try:
            async with database.sessions() as session:
                datasets = await ReplayDatasetRepository(session).list_recent(
                    limit=limit, offset=offset
                )
        except ValueError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        except Exception as error:
            logger.error("replay_dataset_list_failed")
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "replay storage is unavailable"
            ) from error
        return {
            "items": [_dataset_payload(dataset) for dataset in datasets],
            "limit": limit,
            "offset": offset,
        }

    @router.get("/api/v1/replay/sessions")
    async def list_replay_sessions(
        _: Annotated[Principal, Depends(authenticated_principal)],
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, object]:
        try:
            async with database.sessions() as session:
                sessions = await ReplaySessionRepository(session).list_recent(
                    limit=limit, offset=offset
                )
        except Exception as error:
            logger.error("replay_session_list_failed")
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "replay storage is unavailable"
            ) from error
        return {
            "items": [_session_payload(stored) for stored in sessions],
            "limit": limit,
            "offset": offset,
        }

    @router.get("/api/v1/replay/sessions/{session_id}")
    async def replay_snapshot(
        session_id: UUID,
        _: Annotated[Principal, Depends(authenticated_principal)],
    ) -> dict[str, object]:
        try:
            async with database.sessions() as session:
                stored, candles = await _coordinator(session).snapshot(session_id)
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        except ValueError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        except Exception as error:
            logger.error("replay_snapshot_read_failed")
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "replay storage is unavailable"
            ) from error
        result = _session_payload(stored)
        result["candles"] = [candle.model_dump(mode="json") for candle in candles]
        return result

    @router.post("/api/v1/operator/replay/sessions/{session_id}/step")
    async def step_replay_session(
        session_id: UUID,
        payload: ReplayVersionRequest,
        _: Annotated[Principal, Depends(operator_principal)],
    ) -> dict[str, object]:
        try:
            async with database.sessions() as session:
                mutation = await _coordinator(session).step(
                    session_id,
                    expected_version=payload.expected_version,
                    checkpointed_at=datetime.now(UTC),
                )
                await session.commit()
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        except ValueError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        except Exception as error:
            logger.error("replay_step_failed")
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "replay storage is unavailable"
            ) from error
        result = _session_payload(mutation.session)
        result["frame"] = (
            None
            if mutation.frame is None
            else {
                "candle": mutation.frame.candle.model_dump(mode="json"),
                "available_at": mutation.frame.available_at.isoformat(),
                "index": mutation.frame.index,
                "total": mutation.frame.total,
            }
        )
        return result

    @router.post("/api/v1/operator/replay/sessions/{session_id}/seek")
    async def seek_replay_session(
        session_id: UUID,
        payload: ReplaySeekRequest,
        _: Annotated[Principal, Depends(operator_principal)],
    ) -> dict[str, object]:
        try:
            async with database.sessions() as session:
                stored = await _coordinator(session).seek(
                    session_id,
                    as_of=payload.as_of,
                    expected_version=payload.expected_version,
                    checkpointed_at=datetime.now(UTC),
                )
                await session.commit()
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        except ValueError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        except Exception as error:
            logger.error("replay_seek_failed")
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "replay storage is unavailable"
            ) from error
        return _session_payload(stored)

    @router.post(
        "/api/v1/operator/replay/sessions/{session_id}/playback",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def start_replay_playback(
        session_id: UUID,
        payload: ReplayPlaybackRequest,
        _: Annotated[Principal, Depends(operator_principal)],
    ) -> dict[str, object]:
        try:
            async with database.sessions() as session:
                stored = (await _coordinator(session).snapshot(session_id))[0]
            if stored.version != payload.expected_version:
                raise ValueError("replay session version is stale")
            task = await task_manager.start(
                ReplayTaskRequest(
                    session_id,
                    payload.expected_version,
                    payload.candles_per_second,
                    payload.maximum_steps,
                )
            )
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        except ValueError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        except Exception as error:
            logger.error("replay_playback_start_failed")
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "replay storage is unavailable"
            ) from error
        return _task_payload(task, process_owned=True)

    @router.get("/api/v1/replay/sessions/{session_id}/playback")
    async def replay_playback_status(
        session_id: UUID,
        _: Annotated[Principal, Depends(authenticated_principal)],
    ) -> dict[str, object]:
        try:
            task = await task_manager.status(session_id)
            return _task_payload(task, process_owned=task.outcome is ReplayTaskOutcome.RUNNING)
        except KeyError:
            try:
                async with database.sessions() as session:
                    await ReplaySessionRepository(session).load(session_id)
                    task = await ReplayTaskStatusRepository(session).latest_for_session(session_id)
            except KeyError as error:
                raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
            except Exception as error:
                logger.error("replay_playback_status_read_failed")
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE, "replay storage is unavailable"
                ) from error
            return _task_payload(task, process_owned=False)

    @router.get("/api/v1/replay/sessions/{session_id}/playback-runs")
    async def list_replay_playback_runs(
        session_id: UUID,
        _: Annotated[Principal, Depends(authenticated_principal)],
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, object]:
        try:
            async with database.sessions() as session:
                await ReplaySessionRepository(session).load(session_id)
                runs = await ReplayTaskStatusRepository(session).list_for_session(
                    session_id, limit=limit, offset=offset
                )
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        except Exception as error:
            logger.error("replay_playback_history_read_failed")
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "replay storage is unavailable"
            ) from error
        return {
            "items": [_task_payload(run, process_owned=False) for run in runs],
            "limit": limit,
            "offset": offset,
        }

    @router.get("/api/v1/replay/playback-runs/{task_id}")
    async def replay_playback_run(
        task_id: UUID,
        _: Annotated[Principal, Depends(authenticated_principal)],
    ) -> dict[str, object]:
        try:
            async with database.sessions() as session:
                task = await ReplayTaskStatusRepository(session).load(task_id)
            process_owned = False
            try:
                owned = await task_manager.status(task.request.session_id)
                process_owned = (
                    owned.request.task_id == task_id and owned.outcome is ReplayTaskOutcome.RUNNING
                )
                if owned.request.task_id == task_id:
                    task = owned
            except KeyError:
                pass
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        except Exception as error:
            logger.error("replay_playback_run_read_failed")
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "replay storage is unavailable"
            ) from error
        return _task_payload(task, process_owned=process_owned)

    @router.post("/api/v1/operator/replay/sessions/{session_id}/playback/stop")
    async def stop_replay_playback(
        session_id: UUID,
        _: Annotated[Principal, Depends(operator_principal)],
    ) -> dict[str, object]:
        try:
            return _task_payload(await task_manager.stop(session_id), process_owned=False)
        except KeyError:
            try:
                async with database.sessions() as session:
                    await ReplaySessionRepository(session).load(session_id)
                    await ReplayTaskStatusRepository(session).latest_for_session(session_id)
            except KeyError as error:
                raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
            except Exception as error:
                logger.error("replay_playback_stop_lookup_failed")
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE, "replay storage is unavailable"
                ) from error
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "replay playback task is not owned by this process",
            ) from None

    return router


def _coordinator(session: AsyncSession) -> ReplayCoordinator:
    return ReplayCoordinator(ReplaySessionRepository(session), ReplayDatasetRepository(session))


def _session_payload(stored: StoredReplaySession) -> dict[str, object]:
    return {
        "session_id": str(stored.session_id),
        "dataset_sha256": stored.checkpoint.dataset_sha256,
        "instrument_id": str(stored.instrument_id),
        "timeframe_seconds": stored.timeframe_seconds,
        "next_index": stored.checkpoint.next_index,
        "total_events": stored.total_events,
        "version": stored.version,
        "checkpointed_at": stored.checkpointed_at.isoformat(),
    }


def _dataset_payload(dataset: StoredReplayDataset) -> dict[str, object]:
    return {
        "dataset_sha256": dataset.dataset_sha256,
        "instrument_id": str(dataset.instrument_id),
        "timeframe_seconds": dataset.timeframe_seconds,
        "total_events": dataset.total_events,
        "first_timestamp": dataset.first_timestamp.isoformat(),
        "last_timestamp": dataset.last_timestamp.isoformat(),
        "created_at": dataset.created_at.isoformat(),
    }


def _task_payload(task: ReplayTaskStatus, *, process_owned: bool) -> dict[str, object]:
    return {
        "task_id": str(task.request.task_id),
        "session_id": str(task.request.session_id),
        "expected_version": task.request.expected_version,
        "candles_per_second": task.request.candles_per_second,
        "maximum_steps": task.request.maximum_steps,
        "outcome": task.outcome.value,
        "frames_emitted": task.frames_emitted,
        "resulting_version": task.resulting_version,
        "started_at": task.started_at.isoformat(),
        "finished_at": None if task.finished_at is None else task.finished_at.isoformat(),
        "process_owned": process_owned,
    }
