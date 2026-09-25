from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from packages.domain.models import Candle
from packages.replay import ReplayEngine

START = datetime(2026, 9, 24, 3, 45, tzinfo=UTC)
INSTRUMENT_ID = uuid4()


def candles(count: int = 4) -> tuple[Candle, ...]:
    return tuple(
        Candle(
            instrument_id=INSTRUMENT_ID,
            timestamp=START + timedelta(minutes=index),
            timeframe_seconds=60,
            open=Decimal(100 + index),
            high=Decimal(102 + index),
            low=Decimal(99 + index),
            close=Decimal(101 + index),
            volume=Decimal(1000 + index),
        )
        for index in range(count)
    )


def test_replay_steps_prefix_only_and_never_reveals_open_candle_early() -> None:
    engine = ReplayEngine(candles())
    assert engine.snapshot() == ()
    first = engine.step()
    assert first is not None
    assert first.index == 0
    assert first.available_at == START + timedelta(minutes=1)
    assert engine.snapshot() == candles()[:1]
    assert not engine.complete
    engine.seek(START + timedelta(minutes=2, seconds=59))
    assert engine.snapshot() == candles()[:2]
    engine.seek(START)
    assert engine.snapshot() == ()


def test_replay_checkpoint_restores_exact_next_event() -> None:
    original = ReplayEngine(candles())
    original.step()
    original.step()
    checkpoint = original.checkpoint()
    restarted = ReplayEngine(candles())
    restarted.restore(checkpoint)
    assert restarted.snapshot() == candles()[:2]
    assert restarted.step() == original.step()
    while restarted.step() is not None:
        pass
    assert restarted.complete
    assert restarted.step() is None


def test_replay_rejects_invalid_streams_and_checkpoints() -> None:
    with pytest.raises(ValueError, match="at least one"):
        ReplayEngine(())
    with pytest.raises(ValueError, match="closed"):
        ReplayEngine((candles()[0].model_copy(update={"is_closed": False}),))
    with pytest.raises(ValueError, match="timezone-aware"):
        ReplayEngine((candles()[0].model_copy(update={"timestamp": START.replace(tzinfo=None)}),))
    with pytest.raises(ValueError, match="chronological"):
        ReplayEngine(tuple(reversed(candles())))
    other = candles()[0].model_copy(update={"instrument_id": uuid4()})
    with pytest.raises(ValueError, match="one instrument"):
        ReplayEngine((candles()[0], other))
    engine = ReplayEngine(candles())
    with pytest.raises(ValueError, match="timezone-aware"):
        engine.seek(datetime(2026, 9, 24))
    with pytest.raises(ValueError, match="different dataset"):
        engine.restore(ReplayEngine(candles(3)).checkpoint())
    with pytest.raises(ValueError, match="out of range"):
        engine.restore(replace(engine.checkpoint(), next_index=99))
