import asyncio
from collections.abc import Awaitable
from typing import cast

from redis.asyncio import Redis

from packages.config.settings import Settings
from packages.database import Database


async def dependency_checks(database: Database, config: Settings) -> dict[str, bool]:
    checks = {"database": await database.is_ready()}
    if config.redis_required:
        client = Redis.from_url(
            config.redis_url,
            socket_connect_timeout=config.dependency_timeout_seconds,
            socket_timeout=config.dependency_timeout_seconds,
        )
        try:
            async with asyncio.timeout(config.dependency_timeout_seconds):
                checks["redis"] = bool(await cast(Awaitable[bool], client.ping()))
        except Exception:
            checks["redis"] = False
        finally:
            await client.aclose()
    return checks
