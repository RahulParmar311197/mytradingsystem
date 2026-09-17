"""Provider-independent, precision-safe domain contracts.

All datetimes are normalized to UTC at validation boundaries. Monetary amounts,
prices, quantities, and Greeks use Decimal so adapters never introduce binary
floating-point drift into orders or accounting.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("*", mode="before")
    @classmethod
    def normalize_datetimes(cls, value: Any) -> Any:
        if isinstance(value, datetime):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("datetimes must be timezone-aware")
            return value.astimezone(UTC)
        return value


class Exchange(StrEnum):
    NSE = "NSE"
    BSE = "BSE"


class MarketSegment(StrEnum):
    CASH = "CASH"
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"


class OptionType(StrEnum):
    CALL = "CALL"
    PUT = "PUT"


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class SignalAction(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    EXIT = "EXIT"
    HOLD = "HOLD"
    NO_TRADE = "NO_TRADE"


class RiskOutcome(StrEnum):
    APPROVED = "APPROVED"
    RESIZED = "RESIZED"
    REJECTED = "REJECTED"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(StrEnum):
    CREATED = "CREATED"
    RISK_PENDING = "RISK_PENDING"
    RISK_REJECTED = "RISK_REJECTED"
    APPROVED = "APPROVED"
    SUBMITTING = "SUBMITTING"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class Instrument(DomainModel):
    id: UUID = Field(default_factory=uuid4)
    symbol: str = Field(min_length=1, max_length=64)
    exchange: Exchange
    segment: MarketSegment
    isin: str | None = Field(default=None, max_length=12)
    tick_size: Decimal = Field(gt=0)
    lot_size: int = Field(gt=0)
    currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")
    active: bool = True


class Candle(DomainModel):
    instrument_id: UUID
    timestamp: datetime
    timeframe_seconds: int = Field(gt=0)
    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)
    volume: Decimal = Field(ge=0)
    open_interest: Decimal | None = Field(default=None, ge=0)
    is_closed: bool = True

    @model_validator(mode="after")
    def validate_ohlc(self) -> "Candle":
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("impossible OHLC relationship")
        if self.high < self.low:
            raise ValueError("high must not be below low")
        return self


class Tick(DomainModel):
    instrument_id: UUID
    timestamp: datetime
    price: Decimal = Field(gt=0)
    quantity: Decimal = Field(gt=0)
    sequence: int = Field(ge=0)


class Quote(DomainModel):
    instrument_id: UUID
    timestamp: datetime
    bid: Decimal = Field(gt=0)
    ask: Decimal = Field(gt=0)
    bid_quantity: Decimal = Field(ge=0)
    ask_quantity: Decimal = Field(ge=0)
    last: Decimal | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_spread(self) -> "Quote":
        if self.ask < self.bid:
            raise ValueError("ask must not be below bid")
        return self


class OrderBookLevel(DomainModel):
    price: Decimal = Field(gt=0)
    quantity: Decimal = Field(ge=0)
    orders: int = Field(ge=0)


class OrderBookSnapshot(DomainModel):
    instrument_id: UUID
    timestamp: datetime
    bids: tuple[OrderBookLevel, ...]
    asks: tuple[OrderBookLevel, ...]


class OptionContract(DomainModel):
    instrument: Instrument
    underlying_id: UUID
    expiry: date
    strike: Decimal = Field(gt=0)
    option_type: OptionType


class Greeks(DomainModel):
    delta: Decimal
    gamma: Decimal
    theta: Decimal
    vega: Decimal
    rho: Decimal
    implied_volatility: Decimal = Field(ge=0)
    calculated_at: datetime
    model: str = "black_scholes"


class OptionChainEntry(DomainModel):
    contract: OptionContract
    quote: Quote
    open_interest: Decimal = Field(ge=0)
    change_in_open_interest: Decimal
    volume: Decimal = Field(ge=0)
    greeks: Greeks | None = None


class OptionChain(DomainModel):
    underlying_id: UUID
    expiry: date
    timestamp: datetime
    entries: tuple[OptionChainEntry, ...]


class MarketSession(DomainModel):
    exchange: Exchange
    session_date: date
    opens_at: datetime
    closes_at: datetime
    is_trading_day: bool

    @model_validator(mode="after")
    def validate_times(self) -> "MarketSession":
        if self.closes_at <= self.opens_at:
            raise ValueError("session close must follow open")
        return self


class TradingCalendar(DomainModel):
    exchange: Exchange
    timezone_name: str = "Asia/Kolkata"
    sessions: tuple[MarketSession, ...]


class CorporateAction(DomainModel):
    instrument_id: UUID
    action_type: str
    ex_date: date
    ratio: Decimal | None = None
    cash_amount: Decimal | None = None
    source: str


class MarketDataQualityEvent(DomainModel):
    id: UUID = Field(default_factory=uuid4)
    instrument_id: UUID | None = None
    timestamp: datetime
    code: str
    severity: str
    details: dict[str, Any]
    raw_event_id: str | None = None


class Signal(DomainModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime
    instrument_id: UUID
    strategy: str
    strategy_version: str
    action: SignalAction
    confidence: Decimal = Field(ge=0, le=1)
    explanation: str
    data_snapshot_id: str


class StrategyDecision(DomainModel):
    id: UUID = Field(default_factory=uuid4)
    signal_id: UUID
    timestamp: datetime
    action: SignalAction
    confidence: Decimal = Field(ge=0, le=1)
    contributing_factors: dict[str, Decimal]
    rejection_reasons: tuple[str, ...] = ()
    proposed_entry: Decimal | None = None
    proposed_stop: Decimal | None = None
    proposed_targets: tuple[Decimal, ...] = ()
    expected_risk_reward: Decimal | None = None


class RiskDecision(DomainModel):
    id: UUID = Field(default_factory=uuid4)
    order_intent_id: UUID
    timestamp: datetime
    outcome: RiskOutcome
    approved_quantity: Decimal = Field(ge=0)
    reason_codes: tuple[str, ...]
    risk_policy_version: str


class OrderIntent(DomainModel):
    id: UUID = Field(default_factory=uuid4)
    idempotency_key: str = Field(min_length=8, max_length=128)
    decision_id: UUID
    account_id: UUID
    instrument_id: UUID
    side: Side
    order_type: OrderType
    quantity: Decimal = Field(gt=0)
    limit_price: Decimal | None = Field(default=None, gt=0)
    trigger_price: Decimal | None = Field(default=None, gt=0)
    created_at: datetime
    is_exit: bool = False


class BrokerOrder(DomainModel):
    id: UUID = Field(default_factory=uuid4)
    intent_id: UUID
    broker_order_id: str | None = None
    status: OrderStatus
    quantity: Decimal = Field(gt=0)
    filled_quantity: Decimal = Field(ge=0)
    average_price: Decimal | None = Field(default=None, gt=0)
    updated_at: datetime


class Fill(DomainModel):
    id: UUID = Field(default_factory=uuid4)
    broker_order_id: UUID
    broker_fill_id: str
    timestamp: datetime
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(gt=0)
    charges: Decimal = Field(ge=0)


class Position(DomainModel):
    instrument_id: UUID
    quantity: Decimal
    average_price: Decimal = Field(ge=0)
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    updated_at: datetime


class Portfolio(DomainModel):
    account_id: UUID
    cash: Decimal
    positions: tuple[Position, ...]
    gross_exposure: Decimal = Field(ge=0)
    net_exposure: Decimal
    updated_at: datetime


class Trade(DomainModel):
    id: UUID = Field(default_factory=uuid4)
    account_id: UUID
    instrument_id: UUID
    opened_at: datetime
    closed_at: datetime | None = None
    quantity: Decimal = Field(gt=0)
    entry_price: Decimal = Field(gt=0)
    exit_price: Decimal | None = Field(default=None, gt=0)
    realized_pnl: Decimal | None = None


class TradingAccount(DomainModel):
    id: UUID = Field(default_factory=uuid4)
    broker: str
    external_reference: str
    base_currency: str = "INR"
    paper: bool = True
    active: bool = True


class PnLSnapshot(DomainModel):
    account_id: UUID
    timestamp: datetime
    realized: Decimal
    unrealized: Decimal
    equity: Decimal
    drawdown: Decimal = Field(ge=0)


class RiskLimit(DomainModel):
    id: UUID = Field(default_factory=uuid4)
    account_id: UUID
    limit_type: str
    value: Decimal = Field(gt=0)
    enabled: bool = True
    effective_from: datetime


class StrategyConfiguration(DomainModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    version: str
    enabled: bool = False
    parameters: dict[str, Any]
    allowed_instruments: tuple[UUID, ...]


class BacktestRun(DomainModel):
    id: UUID = Field(default_factory=uuid4)
    strategy_configuration_id: UUID
    started_at: datetime
    completed_at: datetime | None = None
    data_from: datetime
    data_to: datetime
    status: str
    metrics: dict[str, Decimal] = Field(default_factory=dict)


class ModelVersion(DomainModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    version: str
    trained_at: datetime
    feature_version: str
    artifact_uri: str
    active: bool = False


class AuditEvent(DomainModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime
    actor_id: str
    action: str
    resource_type: str
    resource_id: str | None = None
    correlation_id: str
    outcome: str
    details: dict[str, Any] = Field(default_factory=dict)
