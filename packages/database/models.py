from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from packages.database.base import AuditMixin, Base, UUIDTimestampMixin


class TradingAccountRecord(UUIDTimestampMixin, Base):
    __tablename__ = "trading_accounts"
    broker: Mapped[str] = mapped_column(String(32), nullable=False)
    external_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    paper: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    __table_args__ = (UniqueConstraint("broker", "external_reference"),)


class RiskLimitRecord(UUIDTimestampMixin, Base):
    __tablename__ = "risk_limits"
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("trading_accounts.id", ondelete="CASCADE"), index=True
    )
    limit_type: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (UniqueConstraint("account_id", "limit_type", "effective_from"),)


class AuditEventRecord(UUIDTimestampMixin, AuditMixin, Base):
    __tablename__ = "audit_events"
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(128))
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class SafetyStateRecord(Base):
    __tablename__ = "safety_state"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(String(256), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)


class InstrumentRecord(UUIDTimestampMixin, Base):
    __tablename__ = "instruments"
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    exchange: Mapped[str] = mapped_column(String(8), nullable=False)
    segment: Mapped[str] = mapped_column(String(16), nullable=False)
    isin: Mapped[str | None] = mapped_column(String(12))
    tick_size: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    lot_size: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    __table_args__ = (UniqueConstraint("exchange", "segment", "symbol"),)


class ExchangeSessionRecord(Base):
    __tablename__ = "exchange_sessions"
    exchange: Mapped[str] = mapped_column(String(8), primary_key=True)
    session_date: Mapped[date] = mapped_column(Date, primary_key=True)
    opens_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_trading_day: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RawCandleRecord(UUIDTimestampMixin, Base):
    __tablename__ = "raw_candles"
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    instrument_id: Mapped[UUID] = mapped_column(ForeignKey("instruments.id"), index=True)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timeframe_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    __table_args__ = (UniqueConstraint("source", "source_event_id"),)


class CandleRecord(UUIDTimestampMixin, Base):
    __tablename__ = "candles"
    instrument_id: Mapped[UUID] = mapped_column(ForeignKey("instruments.id"), index=True)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timeframe_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(28, 8), nullable=False)
    open_interest: Mapped[Decimal | None] = mapped_column(Numeric(28, 8))
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    __table_args__ = (UniqueConstraint("instrument_id", "event_timestamp", "timeframe_seconds"),)


class MarketDataQualityEventRecord(UUIDTimestampMixin, Base):
    __tablename__ = "market_data_quality_events"
    instrument_id: Mapped[UUID | None] = mapped_column(ForeignKey("instruments.id"), index=True)
    event_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    raw_event_id: Mapped[str | None] = mapped_column(String(128))
    __table_args__ = (UniqueConstraint("raw_event_id", "code"),)


class OptionIVObservationRecord(UUIDTimestampMixin, Base):
    __tablename__ = "option_iv_observations"
    instrument_id: Mapped[UUID] = mapped_column(ForeignKey("instruments.id"), index=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    implied_volatility: Mapped[Decimal] = mapped_column(Numeric(18, 10), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    __table_args__ = (
        UniqueConstraint("source", "source_event_id"),
        UniqueConstraint("instrument_id", "observed_at", "source"),
    )


class OptionChainSnapshotRecord(UUIDTimestampMixin, Base):
    __tablename__ = "option_chain_snapshots"
    underlying_id: Mapped[UUID] = mapped_column(ForeignKey("instruments.id"), index=True)
    expiry: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    __table_args__ = (
        UniqueConstraint("source", "source_event_id"),
        UniqueConstraint("underlying_id", "expiry", "observed_at", "source"),
    )


class RawOptionChainRecord(UUIDTimestampMixin, Base):
    __tablename__ = "raw_option_chain_events"
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    __table_args__ = (UniqueConstraint("source", "source_event_id"),)


class PaperOrderRecord(UUIDTimestampMixin, Base):
    __tablename__ = "paper_orders"
    account_id: Mapped[UUID] = mapped_column(ForeignKey("trading_accounts.id"), index=True)
    instrument_id: Mapped[UUID] = mapped_column(ForeignKey("instruments.id"), index=True)
    intent_id: Mapped[UUID] = mapped_column(nullable=False)
    risk_decision_id: Mapped[UUID] = mapped_column(nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(28, 8), nullable=False)
    filled_quantity: Mapped[Decimal] = mapped_column(Numeric(28, 8), nullable=False)
    average_price: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    charges: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (UniqueConstraint("account_id", "idempotency_key"),)


class PaperFillRecord(UUIDTimestampMixin, Base):
    __tablename__ = "paper_fills"
    order_id: Mapped[UUID] = mapped_column(ForeignKey("paper_orders.id"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(28, 8), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    charges: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PaperPositionRecord(UUIDTimestampMixin, Base):
    __tablename__ = "paper_positions"
    account_id: Mapped[UUID] = mapped_column(ForeignKey("trading_accounts.id"), index=True)
    instrument_id: Mapped[UUID] = mapped_column(ForeignKey("instruments.id"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(28, 8), nullable=False)
    average_price: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    __table_args__ = (UniqueConstraint("account_id", "instrument_id"),)


class PaperOrderEventRecord(UUIDTimestampMixin, Base):
    __tablename__ = "paper_order_events"
    order_id: Mapped[UUID] = mapped_column(ForeignKey("paper_orders.id"), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class PaperAccountLedgerRecord(UUIDTimestampMixin, Base):
    __tablename__ = "paper_account_ledgers"
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("trading_accounts.id"), nullable=False, unique=True, index=True
    )
    initial_cash: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    peak_equity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)


class PaperPnLSnapshotRecord(UUIDTimestampMixin, Base):
    __tablename__ = "paper_pnl_snapshots"
    account_id: Mapped[UUID] = mapped_column(ForeignKey("trading_accounts.id"), index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    cash: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    equity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    gross_exposure: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    net_exposure: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    drawdown: Mapped[Decimal] = mapped_column(Numeric(16, 12), nullable=False)


class RiskDecisionRecord(UUIDTimestampMixin, Base):
    __tablename__ = "risk_decisions"
    order_intent_id: Mapped[UUID] = mapped_column(nullable=False, unique=True, index=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("trading_accounts.id"), index=True)
    instrument_id: Mapped[UUID] = mapped_column(ForeignKey("instruments.id"), index=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    approved_quantity: Mapped[Decimal] = mapped_column(Numeric(28, 8), nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)


class ExecutionOrderRecord(UUIDTimestampMixin, Base):
    __tablename__ = "execution_orders"
    quantity: Mapped[Decimal] = mapped_column(Numeric(28, 8), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    filled_quantity: Mapped[Decimal] = mapped_column(Numeric(28, 8), nullable=False)
    broker_order_id: Mapped[str | None] = mapped_column(String(128))
    last_event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    reconciliation_reason: Mapped[str | None] = mapped_column(String(64))


class ExecutionOrderEventRecord(UUIDTimestampMixin, Base):
    __tablename__ = "execution_order_events"
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("execution_orders.id", ondelete="CASCADE"), index=True
    )
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fill_quantity: Mapped[Decimal] = mapped_column(Numeric(28, 8), nullable=False)
    broker_order_id: Mapped[str | None] = mapped_column(String(128))
    resulting_version: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (UniqueConstraint("order_id", "event_id"),)


class MLModelVersionRecord(UUIDTimestampMixin, Base):
    __tablename__ = "ml_model_versions"
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(64), nullable=False)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    artifact_uri: Mapped[str] = mapped_column(String(512), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    stage: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    __table_args__ = (UniqueConstraint("name", "version"),)


class MLPredictionRecord(UUIDTimestampMixin, Base):
    __tablename__ = "ml_predictions"
    model_id: Mapped[UUID] = mapped_column(ForeignKey("ml_model_versions.id"), index=True)
    instrument_id: Mapped[UUID] = mapped_column(ForeignKey("instruments.id"), index=True)
    predicted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    probability: Mapped[Decimal] = mapped_column(Numeric(18, 12), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(64), nullable=False)
    data_snapshot_id: Mapped[str] = mapped_column(String(128), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)


class RevokedAPITokenRecord(UUIDTimestampMixin, Base):
    __tablename__ = "revoked_api_tokens"
    token_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(String(512), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)


class ReplaySessionRecord(UUIDTimestampMixin, Base):
    __tablename__ = "replay_sessions"
    dataset_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    instrument_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    timeframe_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    next_index: Mapped[int] = mapped_column(Integer, nullable=False)
    total_events: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    checkpointed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class ReplayDatasetRecord(Base):
    __tablename__ = "replay_datasets"
    dataset_sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    instrument_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    timeframe_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    total_events: Mapped[int] = mapped_column(Integer, nullable=False)
    first_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    candles: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        CheckConstraint("timeframe_seconds > 0", name="replay_dataset_timeframe_positive"),
        CheckConstraint("total_events > 0", name="replay_dataset_total_positive"),
    )


class ReplayPlaybackRunRecord(Base):
    __tablename__ = "replay_playback_runs"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("replay_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expected_version: Mapped[int] = mapped_column(Integer, nullable=False)
    candles_per_second: Mapped[float] = mapped_column(Float, nullable=False)
    maximum_steps: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    frames_emitted: Mapped[int] = mapped_column(Integer, nullable=False)
    resulting_version: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("expected_version >= 0", name="replay_run_expected_version_nonnegative"),
        CheckConstraint("candles_per_second >= 0.1", name="replay_run_rate_minimum"),
        CheckConstraint("candles_per_second <= 100", name="replay_run_rate_maximum"),
        CheckConstraint("maximum_steps BETWEEN 1 AND 10000", name="replay_run_steps_bounded"),
        CheckConstraint("frames_emitted >= 0", name="replay_run_frames_nonnegative"),
        CheckConstraint(
            "outcome IN ('running', 'complete', 'stopped', 'step_limit', 'failed')",
            name="replay_run_outcome_valid",
        ),
    )
