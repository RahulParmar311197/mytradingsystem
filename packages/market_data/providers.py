"""Provider contracts keep broker payloads outside the normalized domain."""

from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from typing import Protocol

from packages.domain.models import Candle, Instrument


class InstrumentProvider(Protocol):
    async def instruments(self) -> Sequence[Instrument]: ...


class HistoricalMarketDataProvider(Protocol):
    async def candles(
        self,
        instrument: Instrument,
        timeframe_seconds: int,
        start: datetime,
        end: datetime,
    ) -> AsyncIterator[Candle]: ...
