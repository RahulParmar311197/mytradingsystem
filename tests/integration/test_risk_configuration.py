from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database.base import Base
from packages.database.models import (
    AuditEventRecord,
    InstrumentRecord,
    RiskLimitRecord,
    TradingAccountRecord,
)
from packages.domain.models import OrderIntent, OrderType, RiskOutcome, Side
from packages.risk_engine import (
    PersistentRiskAuthority,
    PersistentRiskConfigurationStore,
    PortfolioRiskContext,
    RiskLimitType,
)


@pytest.mark.asyncio
async def test_effective_limits_and_kill_switch_survive_restart() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    account_id, instrument_id = uuid4(), uuid4()
    now = datetime(2026, 9, 18, 5, tzinfo=UTC)
    values = {
        RiskLimitType.MAXIMUM_RISK_PER_TRADE_FRACTION: Decimal("0.01"),
        RiskLimitType.MAXIMUM_DAILY_LOSS_FRACTION: Decimal("0.02"),
        RiskLimitType.MAXIMUM_OPEN_POSITIONS: Decimal(5),
        RiskLimitType.MAXIMUM_INSTRUMENT_EXPOSURE_FRACTION: Decimal("0.2"),
        RiskLimitType.MAXIMUM_QUOTE_AGE_SECONDS: Decimal(5),
        RiskLimitType.MAXIMUM_SPREAD_BPS: Decimal(20),
        RiskLimitType.MAXIMUM_WEEKLY_LOSS_FRACTION: Decimal("0.03"),
        RiskLimitType.MAXIMUM_DRAWDOWN_FRACTION: Decimal("0.1"),
        RiskLimitType.MAXIMUM_GROSS_EXPOSURE_FRACTION: Decimal("0.8"),
        RiskLimitType.MAXIMUM_NET_EXPOSURE_FRACTION: Decimal("0.5"),
        RiskLimitType.MAXIMUM_ORDERS_PER_MINUTE: Decimal(10),
        RiskLimitType.MAXIMUM_CONSECUTIVE_LOSSES: Decimal(3),
        RiskLimitType.MAXIMUM_SECTOR_EXPOSURE_FRACTION: Decimal("0.3"),
        RiskLimitType.MAXIMUM_STRATEGY_ALLOCATION_FRACTION: Decimal("0.2"),
        RiskLimitType.MAXIMUM_SLIPPAGE_BPS: Decimal(25),
        RiskLimitType.MAXIMUM_OPTIONS_EXPOSURE: Decimal("500000"),
        RiskLimitType.MAXIMUM_PORTFOLIO_DELTA: Decimal("1000"),
        RiskLimitType.MAXIMUM_PORTFOLIO_GAMMA: Decimal("100"),
    }
    async with sessions() as session:
        session.add(
            TradingAccountRecord(id=account_id, broker="paper", external_reference="limits")
        )
        session.add(
            InstrumentRecord(
                id=instrument_id,
                symbol="BANKNIFTY",
                exchange="NSE",
                segment="FUTURES",
                tick_size=Decimal("0.05"),
                lot_size=15,
                currency="INR",
                active=True,
            )
        )
        for limit_type, value in values.items():
            session.add(
                RiskLimitRecord(
                    account_id=account_id,
                    limit_type=limit_type.value,
                    value=value,
                    enabled=True,
                    effective_from=now - timedelta(days=1),
                )
            )
        session.add(
            RiskLimitRecord(
                account_id=account_id,
                limit_type=RiskLimitType.MAXIMUM_OPEN_POSITIONS.value,
                value=Decimal(1),
                enabled=True,
                effective_from=now + timedelta(days=1),
            )
        )
        store = PersistentRiskConfigurationStore(session)
        await store.set_kill_switch(
            enabled=True,
            reason="manual incident lock",
            correlation_id="incident-123",
            actor_id="risk-operator",
            occurred_at=now,
        )
        await session.commit()
    async with sessions() as session:
        loaded = await PersistentRiskConfigurationStore(session).load(account_id, now)
        assert loaded.kill_switch_enabled is True
        assert loaded.kill_switch_reason == "manual incident lock"
        assert loaded.limits.maximum_open_positions == 5
        assert loaded.limits.policy_version.startswith("persisted-")
        assert await session.scalar(select(func.count()).select_from(AuditEventRecord)) == 1
        intent = OrderIntent(
            idempotency_key="persisted-config-risk",
            decision_id=uuid4(),
            account_id=account_id,
            instrument_id=instrument_id,
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal(1),
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
        decision = await PersistentRiskAuthority(session).evaluate_with_persisted_configuration(
            intent, context, Decimal("100"), Decimal("98")
        )
        assert decision.outcome is RiskOutcome.REJECTED
        assert "KILL_SWITCH" in decision.reason_codes
        unlocked_context = replace(
            context,
            kill_switch_enabled=False,
            daily_pnl=Decimal(0),
            weekly_pnl=Decimal(0),
            drawdown_fraction=Decimal(0),
            consecutive_losses=0,
        )
        store = PersistentRiskConfigurationStore(session)
        assert (
            await store.activate_automatic_kill_if_required(
                unlocked_context, loaded.limits, correlation_id="auto-safe"
            )
            is False
        )
        breached = replace(unlocked_context, drawdown_fraction=Decimal("0.1"))
        assert (
            await store.activate_automatic_kill_if_required(
                breached, loaded.limits, correlation_id="auto-breach"
            )
            is True
        )
    await engine.dispose()


@pytest.mark.asyncio
async def test_missing_effective_limits_fail_closed() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    account_id = uuid4()
    now = datetime(2026, 9, 18, 5, tzinfo=UTC)
    async with sessions() as session:
        with pytest.raises(RuntimeError, match="missing effective risk limits"):
            await PersistentRiskConfigurationStore(session).load(account_id, now)
    await engine.dispose()
