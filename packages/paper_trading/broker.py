from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.backtesting.engine import BacktestCostModel, GenericCostModel
from packages.database.models import (
    PaperAccountLedgerRecord,
    PaperFillRecord,
    PaperOrderEventRecord,
    PaperOrderRecord,
    PaperPnLSnapshotRecord,
    PaperPositionRecord,
)
from packages.domain.models import (
    OrderIntent,
    OrderStatus,
    OrderType,
    RiskDecision,
    RiskOutcome,
    Side,
)


@dataclass(frozen=True, slots=True)
class PaperExecution:
    order_id: UUID
    status: OrderStatus
    filled_quantity: Decimal
    average_price: Decimal
    charges: Decimal
    duplicate: bool


@dataclass(frozen=True, slots=True)
class PaperPositionMark:
    instrument_id: UUID
    quantity: Decimal
    average_price: Decimal
    market_price: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal


@dataclass(frozen=True, slots=True)
class PaperPortfolioSnapshot:
    account_id: UUID
    occurred_at: datetime
    cash: Decimal
    equity: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    gross_exposure: Decimal
    net_exposure: Decimal
    drawdown: Decimal
    positions: tuple[PaperPositionMark, ...]


class PersistentPaperBroker:
    """Atomic market-order paper fill and accounting service; caller controls commit."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        cost_model: BacktestCostModel | None = None,
        slippage_bps: Decimal = Decimal(0),
    ) -> None:
        if slippage_bps < 0:
            raise ValueError("slippage cannot be negative")
        self.session = session
        self.cost_model = cost_model or GenericCostModel(Decimal(0), Decimal(0))
        self.slippage_bps = slippage_bps

    async def initialize_account(self, account_id: UUID, initial_cash: Decimal) -> None:
        if initial_cash <= 0:
            raise ValueError("initial cash must be positive")
        ledger = await self.session.scalar(
            select(PaperAccountLedgerRecord).where(
                PaperAccountLedgerRecord.account_id == account_id
            )
        )
        if ledger is None:
            self.session.add(
                PaperAccountLedgerRecord(
                    account_id=account_id,
                    initial_cash=initial_cash,
                    cash_balance=initial_cash,
                    peak_equity=initial_cash,
                )
            )
            await self.session.flush()
        elif ledger.initial_cash != initial_cash:
            raise ValueError("paper account is already initialized with different capital")

    async def execute_market(
        self,
        intent: OrderIntent,
        risk: RiskDecision,
        market_price: Decimal,
        occurred_at: datetime,
    ) -> PaperExecution:
        if intent.order_type is not OrderType.MARKET:
            raise ValueError("paper market execution accepts MARKET orders only")
        if risk.order_intent_id != intent.id:
            raise ValueError("risk decision does not belong to order intent")
        if risk.outcome not in (RiskOutcome.APPROVED, RiskOutcome.RESIZED):
            raise PermissionError("independent risk approval is required")
        if risk.approved_quantity <= 0 or risk.approved_quantity > intent.quantity:
            raise ValueError("approved quantity must be within requested quantity")
        if market_price <= 0:
            raise ValueError("market price must be positive")
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError("execution timestamp must be timezone-aware")
        occurred_at = occurred_at.astimezone(UTC)
        existing = await self.session.scalar(
            select(PaperOrderRecord).where(
                PaperOrderRecord.account_id == intent.account_id,
                PaperOrderRecord.idempotency_key == intent.idempotency_key,
            )
        )
        if existing is not None:
            return self._execution(existing, duplicate=True)
        ledger = await self.session.scalar(
            select(PaperAccountLedgerRecord).where(
                PaperAccountLedgerRecord.account_id == intent.account_id
            )
        )
        if ledger is None:
            raise RuntimeError("paper account ledger must be initialized before execution")

        direction = Decimal(1) if intent.side is Side.BUY else Decimal(-1)
        fill_price = market_price * (Decimal(1) + direction * self.slippage_bps / 10000)
        quantity = risk.approved_quantity
        charges = self.cost_model.calculate(fill_price * quantity, intent.side)
        cash_flow = fill_price * quantity
        ledger.cash_balance += (-cash_flow if intent.side is Side.BUY else cash_flow) - charges
        order = PaperOrderRecord(
            id=uuid4(),
            account_id=intent.account_id,
            instrument_id=intent.instrument_id,
            intent_id=intent.id,
            risk_decision_id=risk.id,
            idempotency_key=intent.idempotency_key,
            side=intent.side.value,
            order_type=intent.order_type.value,
            status=OrderStatus.FILLED.value,
            quantity=quantity,
            filled_quantity=quantity,
            average_price=fill_price,
            charges=charges,
            filled_at=occurred_at,
        )
        self.session.add(order)
        self.session.add(
            PaperFillRecord(
                order_id=order.id,
                quantity=quantity,
                price=fill_price,
                charges=charges,
                filled_at=occurred_at,
            )
        )
        self.session.add(
            PaperOrderEventRecord(
                order_id=order.id,
                occurred_at=occurred_at,
                status=OrderStatus.FILLED.value,
                details={"mode": "paper", "risk_decision_id": str(risk.id)},
            )
        )
        await self._update_position(intent, quantity, fill_price, charges)
        await self.session.flush()
        return self._execution(order, duplicate=False)

    async def mark_to_market(
        self, account_id: UUID, prices: dict[UUID, Decimal], occurred_at: datetime
    ) -> PaperPortfolioSnapshot:
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError("snapshot timestamp must be timezone-aware")
        occurred_at = occurred_at.astimezone(UTC)
        ledger = await self.session.scalar(
            select(PaperAccountLedgerRecord).where(
                PaperAccountLedgerRecord.account_id == account_id
            )
        )
        if ledger is None:
            raise RuntimeError("paper account ledger is not initialized")
        positions = tuple(
            (
                await self.session.scalars(
                    select(PaperPositionRecord).where(
                        PaperPositionRecord.account_id == account_id,
                    )
                )
            ).all()
        )
        marks: list[PaperPositionMark] = []
        market_value = realized = unrealized = gross = net = Decimal(0)
        for position in positions:
            realized += position.realized_pnl
            if position.quantity == 0:
                continue
            price = prices.get(position.instrument_id)
            if price is None or price <= 0:
                raise ValueError(f"valid price required for open position {position.instrument_id}")
            value = position.quantity * price
            pnl = (price - position.average_price) * position.quantity
            market_value += value
            unrealized += pnl
            gross += abs(value)
            net += value
            marks.append(
                PaperPositionMark(
                    position.instrument_id,
                    position.quantity,
                    position.average_price,
                    price,
                    position.realized_pnl,
                    pnl,
                )
            )
        equity = ledger.cash_balance + market_value
        ledger.peak_equity = max(ledger.peak_equity, equity)
        drawdown = (
            (ledger.peak_equity - equity) / ledger.peak_equity
            if ledger.peak_equity > 0
            else Decimal(0)
        )
        self.session.add(
            PaperPnLSnapshotRecord(
                account_id=account_id,
                occurred_at=occurred_at,
                cash=ledger.cash_balance,
                realized_pnl=realized,
                unrealized_pnl=unrealized,
                equity=equity,
                gross_exposure=gross,
                net_exposure=net,
                drawdown=drawdown,
            )
        )
        await self.session.flush()
        return PaperPortfolioSnapshot(
            account_id,
            occurred_at,
            ledger.cash_balance,
            equity,
            realized,
            unrealized,
            gross,
            net,
            drawdown,
            tuple(marks),
        )

    async def _update_position(
        self, intent: OrderIntent, fill_quantity: Decimal, price: Decimal, charges: Decimal
    ) -> None:
        position = await self.session.scalar(
            select(PaperPositionRecord).where(
                PaperPositionRecord.account_id == intent.account_id,
                PaperPositionRecord.instrument_id == intent.instrument_id,
            )
        )
        if position is None:
            signed = fill_quantity if intent.side is Side.BUY else -fill_quantity
            self.session.add(
                PaperPositionRecord(
                    account_id=intent.account_id,
                    instrument_id=intent.instrument_id,
                    quantity=signed,
                    average_price=price,
                    realized_pnl=-charges,
                )
            )
            return
        old_quantity = position.quantity
        delta = fill_quantity if intent.side is Side.BUY else -fill_quantity
        new_quantity = old_quantity + delta
        same_direction = old_quantity == 0 or (old_quantity > 0) == (delta > 0)
        if same_direction:
            total = abs(old_quantity) + abs(delta)
            position.average_price = (
                abs(old_quantity) * position.average_price + abs(delta) * price
            ) / total
        else:
            closed = min(abs(old_quantity), abs(delta))
            sign = Decimal(1) if old_quantity > 0 else Decimal(-1)
            position.realized_pnl += (price - position.average_price) * closed * sign
            if new_quantity == 0:
                position.average_price = Decimal(0)
            elif (new_quantity > 0) != (old_quantity > 0):
                position.average_price = price
        position.quantity = new_quantity
        position.realized_pnl -= charges

    @staticmethod
    def _execution(order: PaperOrderRecord, *, duplicate: bool) -> PaperExecution:
        return PaperExecution(
            order.id,
            OrderStatus(order.status),
            order.filled_quantity,
            order.average_price,
            order.charges,
            duplicate,
        )
