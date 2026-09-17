import asyncio
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

SCHEMA_REVISION = "0003_operations"


class Database:
    def __init__(self, url: str) -> None:
        self.engine: AsyncEngine = create_async_engine(
            url, pool_pre_ping=True, hide_parameters=True
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessions() as session:
            yield session

    async def is_ready(self) -> bool:
        try:
            async with asyncio.timeout(2), self.engine.connect() as connection:
                versions = (
                    (await connection.execute(text("SELECT version_num FROM alembic_version")))
                    .scalars()
                    .all()
                )
                await connection.execute(text("SELECT key FROM safety_state LIMIT 1"))
                await connection.execute(text("SELECT id FROM audit_events LIMIT 1"))
                return list(versions) == [SCHEMA_REVISION]
        except Exception:
            return False

    async def close(self) -> None:
        await self.engine.dispose()
