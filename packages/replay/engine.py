"""Closed-candle replay with prefix-only snapshots and restart checkpoints."""

from bisect import bisect_right
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID

from packages.domain.models import Candle


@dataclass(frozen=True, slots=True)
class ReplayCheckpoint:
    dataset_sha256: str
    next_index: int


@dataclass(frozen=True, slots=True)
class ReplayFrame:
    candle: Candle
    available_at: datetime
    index: int
    total: int


class ReplayEngine:
    """Replay one closed candle stream without exposing future observations."""

    def __init__(self, candles: tuple[Candle, ...]) -> None:
        if not candles:
            raise ValueError("replay requires at least one candle")
        if any(not candle.is_closed for candle in candles):
            raise ValueError("replay accepts closed candles only")
        stream = {(candle.instrument_id, candle.timeframe_seconds) for candle in candles}
        if len(stream) != 1:
            raise ValueError("replay candles must belong to one instrument and timeframe")
        timestamps = tuple(candle.timestamp for candle in candles)
        if any(
            timestamp.tzinfo is None or timestamp.utcoffset() is None for timestamp in timestamps
        ):
            raise ValueError("replay candle timestamps must be timezone-aware")
        if timestamps != tuple(sorted(timestamps)) or len(set(timestamps)) != len(timestamps):
            raise ValueError("replay candles must have unique chronological timestamps")
        self._candles = candles
        self._available_at = tuple(
            candle.timestamp + timedelta(seconds=candle.timeframe_seconds) for candle in candles
        )
        self._dataset_sha256 = _dataset_digest(candles)
        self._next_index = 0

    @property
    def dataset_sha256(self) -> str:
        return self._dataset_sha256

    @property
    def instrument_id(self) -> UUID:
        return self._candles[0].instrument_id

    @property
    def timeframe_seconds(self) -> int:
        return self._candles[0].timeframe_seconds

    @property
    def total(self) -> int:
        return len(self._candles)

    @property
    def complete(self) -> bool:
        return self._next_index == len(self._candles)

    def step(self) -> ReplayFrame | None:
        if self.complete:
            return None
        index = self._next_index
        self._next_index += 1
        return ReplayFrame(
            self._candles[index], self._available_at[index], index, len(self._candles)
        )

    def snapshot(self) -> tuple[Candle, ...]:
        """Return only candles already emitted or exposed by an explicit seek."""
        return self._candles[: self._next_index]

    def seek(self, as_of: datetime) -> tuple[Candle, ...]:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("replay seek timestamp must be timezone-aware")
        self._next_index = bisect_right(self._available_at, as_of.astimezone(UTC))
        return self.snapshot()

    def checkpoint(self) -> ReplayCheckpoint:
        return ReplayCheckpoint(self._dataset_sha256, self._next_index)

    def restore(self, checkpoint: ReplayCheckpoint) -> None:
        if checkpoint.dataset_sha256 != self._dataset_sha256:
            raise ValueError("replay checkpoint belongs to a different dataset")
        if not 0 <= checkpoint.next_index <= len(self._candles):
            raise ValueError("replay checkpoint index is out of range")
        self._next_index = checkpoint.next_index


def _dataset_digest(candles: tuple[Candle, ...]) -> str:
    digest = sha256()
    for candle in candles:
        encoded = candle.model_dump_json().encode()
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()
