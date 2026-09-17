from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select, text

from apps.worker.main import run_once
from packages.config import Settings
from packages.database import Database
from packages.database.models import (
    AuditEventRecord,
    RiskLimitRecord,
    ServiceHeartbeatRecord,
    TradingAccountRecord,
)
from packages.operations.service import read_safety, set_kill_switch


async def test_unmigrated_database_is_not_ready(tmp_path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'empty.db'}")
    assert not await database.is_ready()
    await database.close()


async def test_kill_switch_risk_limits_audit_and_worker_survive_restart(migrated_url: str) -> None:
    database = Database(migrated_url)
    assert await database.is_ready()
    account_id = uuid4()
    async with database.sessions.begin() as session:
        assert (await read_safety(session)).entries_locked
        session.add(
            TradingAccountRecord(
                id=account_id, broker="paper", external_reference="test", paper=True, active=True
            )
        )
        await session.flush()
        session.add(
            RiskLimitRecord(
                account_id=account_id,
                limit_type="max_risk_fraction",
                value=Decimal("0.0025"),
                enabled=True,
                effective_from=datetime.now(UTC),
            )
        )
        await set_kill_switch(
            session,
            enabled=True,
            reason="Recovery verification",
            actor="operator",
            correlation_id="restart-test",
        )
    assert await run_once(database, Settings(_env_file=None, database_url=migrated_url))
    await database.close()
    restarted = Database(migrated_url)
    async with restarted.sessions() as session:
        safety = await read_safety(session)
        assert safety.entries_locked and safety.reason == "Recovery verification"
        assert await session.scalar(select(func.count()).select_from(AuditEventRecord)) == 1
        limit = await session.scalar(select(RiskLimitRecord))
        assert limit and limit.value == Decimal("0.0025")
        heartbeat = await session.get(ServiceHeartbeatRecord, "worker")
        assert heartbeat and heartbeat.healthy
    await restarted.close()


async def test_safety_change_rolls_back_when_audit_transaction_fails(migrated_url: str) -> None:
    database = Database(migrated_url)
    async with database.sessions() as session:
        await set_kill_switch(
            session,
            enabled=False,
            reason="Uncommitted unlock",
            actor="operator",
            correlation_id="rollback-test",
        )
        await session.rollback()
    async with database.sessions() as session:
        assert (await read_safety(session)).entries_locked
        assert await session.scalar(select(func.count()).select_from(AuditEventRecord)) == 0
        await session.execute(text("DELETE FROM safety_state"))
        await session.commit()
        assert (await read_safety(session)).entries_locked
    await database.close()
