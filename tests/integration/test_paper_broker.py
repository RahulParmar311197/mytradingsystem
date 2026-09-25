from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database.base import Base
from packages.database.models import (
    InstrumentRecord,
    PaperAccountLedgerRecord,
    PaperFillRecord,
    PaperOrderEventRecord,
    PaperOrderRecord,
    PaperPnLSnapshotRecord,
    PaperPositionRecord,
    TradingAccountRecord,
)
from packages.domain.models import OrderIntent, OrderType, RiskDecision, RiskOutcome, Side
from packages.paper_trading import PersistentPaperBroker


@pytest.mark.asyncio
async def test_paper_market_fill_is_risk_gated_idempotent_and_restart_safe() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    account_id, instrument_id = uuid4(), uuid4()
    now = datetime(2026, 9, 18, 4, tzinfo=UTC)
    async with sessions() as session:
        session.add(TradingAccountRecord(id=account_id, broker="paper", external_reference="test"))
        session.add(
            InstrumentRecord(
                id=instrument_id,
                symbol="RELIANCE",
                exchange="NSE",
                segment="CASH",
                tick_size=Decimal("0.05"),
                lot_size=1,
                currency="INR",
                active=True,
            )
        )
        await session.commit()
    intent = OrderIntent(
        idempotency_key="paper-order-0001",
        decision_id=uuid4(),
        account_id=account_id,
        instrument_id=instrument_id,
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("10"),
        created_at=now,
    )
    risk = RiskDecision(
        order_intent_id=intent.id,
        timestamp=now,
        outcome=RiskOutcome.RESIZED,
        approved_quantity=Decimal("4"),
        reason_codes=("POSITION_SIZE_REDUCED",),
        risk_policy_version="test-v1",
    )
    async with sessions() as session:
        broker = PersistentPaperBroker(session, slippage_bps=Decimal("10"))
        await broker.initialize_account(account_id, Decimal("10000"))
        first = await broker.execute_market(intent, risk, Decimal("100"), now)
        snapshot = await broker.mark_to_market(account_id, {instrument_id: Decimal("101")}, now)
        await session.commit()
        assert first.filled_quantity == Decimal("4")
        assert first.average_price == Decimal("100.1")
        assert snapshot.cash == Decimal("9599.6")
        assert snapshot.unrealized_pnl == Decimal("3.6")
        assert snapshot.equity == Decimal("10003.6")
        assert snapshot.gross_exposure == Decimal("404")
    # A new session simulates process restart; the idempotency record survives it.
    async with sessions() as session:
        duplicate = await PersistentPaperBroker(session).execute_market(
            intent, risk, Decimal("999"), now
        )
        assert duplicate.order_id == first.order_id
        assert duplicate.duplicate is True
        assert await session.scalar(select(func.count()).select_from(PaperOrderRecord)) == 1
        assert await session.scalar(select(func.count()).select_from(PaperFillRecord)) == 1
        assert await session.scalar(select(func.count()).select_from(PaperOrderEventRecord)) == 1
        assert await session.scalar(select(func.count()).select_from(PaperAccountLedgerRecord)) == 1
        assert await session.scalar(select(func.count()).select_from(PaperPnLSnapshotRecord)) == 1
        position = await session.scalar(select(PaperPositionRecord))
        assert position is not None
        assert position.quantity == Decimal("4")
        assert position.average_price == Decimal("100.1")
    await engine.dispose()


@pytest.mark.asyncio
async def test_paper_broker_refuses_missing_or_mismatched_risk_approval() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime(2026, 9, 18, 4, tzinfo=UTC)
    intent = OrderIntent(
        idempotency_key="paper-order-0002",
        decision_id=uuid4(),
        account_id=uuid4(),
        instrument_id=uuid4(),
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal(1),
        created_at=now,
    )
    rejected = RiskDecision(
        order_intent_id=intent.id,
        timestamp=now,
        outcome=RiskOutcome.REJECTED,
        approved_quantity=Decimal(0),
        reason_codes=("TEST_REJECTION",),
        risk_policy_version="test-v1",
    )
    async with sessions() as session:
        with pytest.raises(PermissionError, match="risk approval"):
            await PersistentPaperBroker(session).execute_market(
                intent, rejected, Decimal("100"), now
            )
        mismatched = rejected.model_copy(
            update={
                "order_intent_id": uuid4(),
                "outcome": RiskOutcome.APPROVED,
                "approved_quantity": Decimal(1),
            }
        )
        with pytest.raises(ValueError, match="does not belong"):
            await PersistentPaperBroker(session).execute_market(
                intent, mismatched, Decimal("100"), now
            )
        assert await session.scalar(select(func.count()).select_from(PaperOrderRecord)) == 0
    await engine.dispose()
