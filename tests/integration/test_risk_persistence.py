from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database.base import Base
from packages.database.models import (
    InstrumentRecord,
    RiskDecisionRecord,
    TradingAccountRecord,
)
from packages.domain.models import OrderIntent, OrderType, Side
from packages.risk_engine import (
    PersistentRiskAuthority,
    PortfolioRiskContext,
    RiskEvaluationRequest,
    RiskLimits,
)


@pytest.mark.asyncio
async def test_risk_decision_is_idempotent_across_restart_and_inputs_are_immutable() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    account_id, instrument_id = uuid4(), uuid4()
    now = datetime(2026, 9, 18, 5, tzinfo=UTC)
    async with sessions() as session:
        session.add(TradingAccountRecord(id=account_id, broker="paper", external_reference="risk"))
        session.add(
            InstrumentRecord(
                id=instrument_id,
                symbol="NIFTY",
                exchange="NSE",
                segment="FUTURES",
                tick_size=Decimal("0.05"),
                lot_size=25,
                currency="INR",
                active=True,
            )
        )
        await session.commit()
    intent = OrderIntent(
        idempotency_key="persistent-risk-1",
        decision_id=uuid4(),
        account_id=account_id,
        instrument_id=instrument_id,
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("10"),
        created_at=now,
    )
    context = PortfolioRiskContext(
        now,
        Decimal("100000"),
        Decimal(0),
        0,
        Decimal(0),
        Decimal(0),
        now - timedelta(seconds=1),
        Decimal("99.95"),
        Decimal("100.05"),
        True,
        True,
        True,
    )
    request = RiskEvaluationRequest(
        intent,
        context,
        RiskLimits(
            "persist-v1", Decimal("0.01"), Decimal("0.02"), 5, Decimal("0.5"), 5, Decimal("20")
        ),
        Decimal("100"),
        Decimal("98"),
    )
    async with sessions() as session:
        first = await PersistentRiskAuthority(session).evaluate(request)
        await session.commit()
    async with sessions() as session:
        second = await PersistentRiskAuthority(session).evaluate(request)
        assert second == first
        assert await session.scalar(select(func.count()).select_from(RiskDecisionRecord)) == 1
        changed = replace(request, stop_price=Decimal("99"))
        with pytest.raises(ValueError, match="different risk inputs"):
            await PersistentRiskAuthority(session).evaluate(changed)
        assert await session.scalar(select(func.count()).select_from(RiskDecisionRecord)) == 1
    await engine.dispose()
