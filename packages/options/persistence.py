"""Idempotent point-in-time persistence for option implied-volatility history."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models import (
    OptionChainSnapshotRecord,
    OptionIVObservationRecord,
    RawOptionChainRecord,
)
from packages.domain.models import OptionChain
from packages.options.analytics import ImpliedVolatilityObservation, put_call_ratio


class OptionChainSnapshotRepository:
    """Persist immutable normalized chain snapshots with provider idempotency."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ingest(
        self,
        chain: OptionChain,
        *,
        source: str,
        source_event_id: str,
        raw_payload: dict[str, object],
    ) -> OptionChain:
        put_call_ratio(chain)  # runs strict chain identity and point-in-time validation
        if not source.strip() or not source_event_id.strip():
            raise ValueError("chain source and source event ID are required")
        if not raw_payload:
            raise ValueError("raw chain payload is required")
        payload = chain.model_dump(mode="json")
        raw_existing = await self.session.scalar(
            select(RawOptionChainRecord).where(
                RawOptionChainRecord.source == source,
                RawOptionChainRecord.source_event_id == source_event_id,
            )
        )
        existing = await self.session.scalar(
            select(OptionChainSnapshotRecord).where(
                OptionChainSnapshotRecord.source == source,
                OptionChainSnapshotRecord.source_event_id == source_event_id,
            )
        )
        if existing is not None:
            if raw_existing is None:
                raise ValueError("normalized chain exists without its raw provider event")
            if existing.payload != payload or raw_existing.payload != raw_payload:
                raise ValueError("chain source event already exists with different content")
            return OptionChain.model_validate(existing.payload)
        if raw_existing is not None:
            raise ValueError("raw chain event exists without its normalized snapshot")
        self.session.add(
            RawOptionChainRecord(
                source=source,
                source_event_id=source_event_id,
                received_at=chain.timestamp,
                payload=raw_payload,
            )
        )
        self.session.add(
            OptionChainSnapshotRecord(
                underlying_id=chain.underlying_id,
                expiry=chain.expiry,
                observed_at=chain.timestamp,
                source=source,
                source_event_id=source_event_id,
                payload=payload,
            )
        )
        await self.session.flush()
        return chain

    async def latest_as_of(
        self, underlying_id: UUID, expiry: date, as_of: datetime
    ) -> OptionChain | None:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("chain cutoff must be timezone-aware")
        record = await self.session.scalar(
            select(OptionChainSnapshotRecord)
            .where(
                OptionChainSnapshotRecord.underlying_id == underlying_id,
                OptionChainSnapshotRecord.expiry == expiry,
                OptionChainSnapshotRecord.observed_at <= as_of,
            )
            .order_by(OptionChainSnapshotRecord.observed_at.desc())
            .limit(1)
        )
        return OptionChain.model_validate(record.payload) if record is not None else None


class OptionIVHistoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ingest(
        self,
        *,
        instrument_id: UUID,
        observed_at: datetime,
        implied_volatility: Decimal,
        source: str,
        source_event_id: str,
    ) -> ImpliedVolatilityObservation:
        observation = ImpliedVolatilityObservation(observed_at, implied_volatility)
        if not source.strip() or not source_event_id.strip():
            raise ValueError("IV source and source event ID are required")
        existing = await self.session.scalar(
            select(OptionIVObservationRecord).where(
                OptionIVObservationRecord.source == source,
                OptionIVObservationRecord.source_event_id == source_event_id,
            )
        )
        if existing is not None:
            if (
                existing.instrument_id != instrument_id
                or self._aware(existing.observed_at) != observation.observed_at.astimezone(UTC)
                or existing.implied_volatility != implied_volatility
            ):
                raise ValueError("IV source event already exists with different content")
            return self._domain(existing)
        self.session.add(
            OptionIVObservationRecord(
                instrument_id=instrument_id,
                observed_at=observed_at,
                implied_volatility=implied_volatility,
                source=source,
                source_event_id=source_event_id,
            )
        )
        await self.session.flush()
        return observation

    async def history_as_of(
        self, instrument_id: UUID, as_of: datetime, *, limit: int = 252
    ) -> tuple[ImpliedVolatilityObservation, ...]:
        if as_of.tzinfo is None or as_of.utcoffset() is None or limit <= 0:
            raise ValueError("history cutoff must be timezone-aware and limit positive")
        records = tuple(
            (
                await self.session.scalars(
                    select(OptionIVObservationRecord)
                    .where(
                        OptionIVObservationRecord.instrument_id == instrument_id,
                        OptionIVObservationRecord.observed_at <= as_of,
                    )
                    .order_by(OptionIVObservationRecord.observed_at.desc())
                    .limit(limit)
                )
            ).all()
        )
        return tuple(self._domain(record) for record in reversed(records))

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @classmethod
    def _domain(cls, record: OptionIVObservationRecord) -> ImpliedVolatilityObservation:
        return ImpliedVolatilityObservation(
            cls._aware(record.observed_at), record.implied_volatility
        )
