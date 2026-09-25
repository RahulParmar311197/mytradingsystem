"""Replay orchestration over immutable datasets and persisted checkpoints."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from packages.domain.models import Candle
from packages.replay.engine import ReplayEngine, ReplayFrame
from packages.replay.persistence import ReplaySessionRepository, StoredReplaySession


class ReplayDatasetLoader(Protocol):
    """Load one immutable candle dataset by its content identity."""

    async def load(self, dataset_sha256: str) -> tuple[Candle, ...]: ...


@dataclass(frozen=True, slots=True)
class ReplayMutation:
    session: StoredReplaySession
    frame: ReplayFrame | None


class ReplayCoordinator:
    """Reconstruct, mutate, and atomically checkpoint a replay session."""

    def __init__(
        self, repository: ReplaySessionRepository, dataset_loader: ReplayDatasetLoader
    ) -> None:
        self.repository = repository
        self.dataset_loader = dataset_loader

    async def step(
        self,
        session_id: UUID,
        *,
        expected_version: int,
        checkpointed_at: datetime,
    ) -> ReplayMutation:
        stored, engine = await self._restore(session_id)
        if stored.version != expected_version:
            raise ValueError("replay session version is stale")
        frame = engine.step()
        if frame is None:
            return ReplayMutation(stored, None)
        saved = await self.repository.save(
            session_id,
            engine.checkpoint(),
            expected_version=expected_version,
            checkpointed_at=checkpointed_at,
        )
        return ReplayMutation(saved, frame)

    async def seek(
        self,
        session_id: UUID,
        *,
        as_of: datetime,
        expected_version: int,
        checkpointed_at: datetime,
    ) -> StoredReplaySession:
        stored, engine = await self._restore(session_id)
        if stored.version != expected_version:
            raise ValueError("replay session version is stale")
        engine.seek(as_of)
        if engine.checkpoint() == stored.checkpoint:
            return stored
        return await self.repository.save(
            session_id,
            engine.checkpoint(),
            expected_version=expected_version,
            checkpointed_at=checkpointed_at,
        )

    async def snapshot(self, session_id: UUID) -> tuple[StoredReplaySession, tuple[Candle, ...]]:
        stored, engine = await self._restore(session_id)
        return stored, engine.snapshot()

    async def _restore(self, session_id: UUID) -> tuple[StoredReplaySession, ReplayEngine]:
        stored = await self.repository.load(session_id)
        candles = await self.dataset_loader.load(stored.checkpoint.dataset_sha256)
        engine = ReplayEngine(candles)
        if (
            engine.dataset_sha256 != stored.checkpoint.dataset_sha256
            or engine.instrument_id != stored.instrument_id
            or engine.timeframe_seconds != stored.timeframe_seconds
            or engine.total != stored.total_events
        ):
            raise ValueError("replay dataset no longer matches persisted session evidence")
        engine.restore(stored.checkpoint)
        return stored, engine
