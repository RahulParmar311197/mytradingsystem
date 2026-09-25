"""Exercise the documented Alembic chain from an empty local database."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def test_clean_sqlite_database_reaches_latest_revision(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    database = tmp_path / "migrated.db"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "infra/migrations/alembic.ini", "upgrade", "head"],
        cwd=root,
        env={**os.environ, "MTS_DATABASE_URL": f"sqlite+aiosqlite:///{database}"},
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0016_exchange_sessions",
        )
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name='exchange_sessions'"
            ).fetchone()
            is not None
        )
        columns = connection.execute("PRAGMA table_info(revoked_api_tokens)").fetchall()
        assert next(row for row in columns if row[1] == "correlation_id")[4] is None
