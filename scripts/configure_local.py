"""Create an ignored local environment with random credentials; never overwrite it."""

import os
import secrets
from pathlib import Path


def main() -> None:
    owner = secrets.token_urlsafe(32)
    app = secrets.token_urlsafe(32)
    text = (
        "MTS_ENVIRONMENT=development\nMTS_TRADING_MODE=paper\nMTS_LIVE_TRADING_ENABLED=false\n"
        f"MTS_DB_OWNER_PASSWORD={owner}\nMTS_DB_APP_PASSWORD={app}\n"
        f"MTS_DATABASE_URL=postgresql+asyncpg://mts_app:{app}@localhost:5432/mts\n"
        f"MTS_MIGRATION_DATABASE_URL=postgresql+asyncpg://mts_owner:{owner}@localhost:5432/mts\n"
        "MTS_REDIS_URL=redis://localhost:6379/0\nMTS_REDIS_REQUIRED=true\n"
        'MTS_CORS_ORIGINS=["http://localhost:3000"]\n'
    )
    fd = os.open(Path(".env"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as output:
        output.write(text)
    print("Created .env. Keep it private and run the documented migrations.")


if __name__ == "__main__":
    main()
