import argparse
import asyncio
import logging
import signal

from packages.config import Settings
from packages.config.settings import TradingMode
from packages.database import Database
from packages.observability.dependencies import dependency_checks
from packages.observability.logging import configure_logging
from packages.operations.service import record_heartbeat

logger = logging.getLogger(__name__)


async def run_once(database: Database, config: Settings) -> bool:
    checks = await dependency_checks(database, config)
    healthy = all(checks.values())
    if checks["database"]:
        async with database.sessions.begin() as session:
            await record_heartbeat(session, healthy=healthy, checks=checks)
    logger.info(
        "worker_health", extra={"checks": checks, "trading_mode": config.trading_mode.value}
    )
    return healthy


async def run(*, once: bool = False) -> int:
    config = Settings()
    if config.trading_mode is TradingMode.LIVE:
        raise RuntimeError("live execution is unavailable in this release")
    configure_logging(config.log_level)
    database = Database(config.database_url)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    try:
        while not stop.is_set():
            try:
                healthy = await run_once(database, config)
            except Exception:
                healthy = False
                logger.exception("worker_cycle_failed")
            if once:
                return 0 if healthy else 1
            try:
                await asyncio.wait_for(stop.wait(), timeout=config.worker_interval_seconds)
            except TimeoutError:
                continue
        return 0
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run dependency monitor and durable heartbeat worker"
    )
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(once=args.once)))


if __name__ == "__main__":
    main()
