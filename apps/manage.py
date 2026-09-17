"""Explicit local operator commands. No broker or live-order access."""

import argparse
import asyncio
import json
from uuid import uuid4

from packages.config import Settings
from packages.config.settings import TradingMode
from packages.database import Database
from packages.operations.service import read_safety, set_kill_switch


async def execute(args: argparse.Namespace) -> None:
    settings = Settings()
    if settings.trading_mode is TradingMode.LIVE:
        raise RuntimeError("live execution is unavailable in this release")
    database = Database(settings.database_url)
    try:
        if not await database.is_ready():
            raise RuntimeError("database unavailable or migrations incomplete")
        async with database.sessions.begin() as session:
            if args.command == "safety":
                result = await read_safety(session)
            else:
                result = await set_kill_switch(
                    session,
                    enabled=args.state == "on",
                    reason=args.reason,
                    actor="local-operator",
                    correlation_id=str(uuid4()),
                )
        print(json.dumps(result.model_dump(mode="json")))
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("safety")
    kill = commands.add_parser("kill-switch")
    kill.add_argument("state", choices=["on", "off"])
    kill.add_argument("--reason", required=True)
    asyncio.run(execute(parser.parse_args()))


if __name__ == "__main__":
    main()
