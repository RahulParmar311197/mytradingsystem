import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def migrated_url(tmp_path: Path) -> str:
    url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "infra/migrations/alembic.ini", "upgrade", "head"],
        env={
            **os.environ,
            "MTS_DATABASE_URL": url,
            "MTS_TRADING_MODE": "paper",
            "MTS_LIVE_TRADING_ENABLED": "false",
            "MTS_ENVIRONMENT": "test",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return url
