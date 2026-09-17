"""Opt-in real PostgreSQL gate; CI supplies a dedicated disposable database."""

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from packages.database import Database
from packages.database.models import AuditEventRecord
from packages.operations.service import read_safety, set_kill_switch


@pytest.mark.skipif(
    not os.environ.get("TEST_POSTGRES_URL"), reason="dedicated PostgreSQL not configured"
)
async def test_postgres_migrations_transactions_and_restart() -> None:
    url = os.environ["TEST_POSTGRES_URL"]
    database = Database(url)
    assert await database.is_ready()
    correlation = str(uuid4())
    async with database.sessions.begin() as session:
        result = await set_kill_switch(
            session,
            enabled=True,
            reason="CI PostgreSQL validation",
            actor="ci",
            correlation_id=correlation,
        )
        assert result.entries_locked
        assert result.updated_at and result.updated_at.tzinfo is UTC
    await database.close()
    restarted = Database(url)
    async with restarted.sessions() as session:
        assert (await read_safety(session)).entries_locked
        event = await session.scalar(
            select(AuditEventRecord).where(AuditEventRecord.correlation_id == correlation)
        )
        assert event and event.occurred_at <= datetime.now(UTC)
    await restarted.close()
