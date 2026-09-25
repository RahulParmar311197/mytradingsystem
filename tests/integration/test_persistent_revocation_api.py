from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from apps.api.main import create_app
from packages.auth import PersistentTokenRevocationStore
from packages.config import Settings
from packages.database import Base, Database
from packages.database.models import AuditEventRecord, RevokedAPITokenRecord

VIEWER = "viewer-token-that-is-at-least-32-characters"
OPERATOR = "operator-token-that-is-at-least-32-characters"


async def configured_database(path: Path, *, revoke_viewer: bool = True) -> Database:
    database = Database(f"sqlite+aiosqlite:///{path}")
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    if revoke_viewer:
        async with database.sessions() as session:
            await PersistentTokenRevocationStore(session).revoke(
                token_sha256=sha256(VIEWER.encode()).hexdigest(),
                revoked_at=datetime(2026, 9, 24, tzinfo=UTC),
                actor_id="security-operator",
                reason="credential exposed",
                correlation_id="incident-123",
            )
            await session.commit()
    return database


@pytest.mark.asyncio
async def test_protected_api_checks_persistent_revocation_on_every_request(
    tmp_path: Path,
) -> None:
    database = await configured_database(tmp_path / "auth.db")
    app = create_app(
        Settings(
            database_url=str(database.engine.url),
            api_viewer_token=VIEWER,
            api_operator_token=OPERATOR,
            api_persistent_revocation_enabled=True,
        ),
        database,
    )
    with TestClient(app) as client:
        revoked = client.get("/api/v1/session", headers={"Authorization": f"Bearer {VIEWER}"})
        assert revoked.status_code == 401
        assert revoked.headers["www-authenticate"] == "Bearer"
        operator = client.get("/api/v1/session", headers={"Authorization": f"Bearer {OPERATOR}"})
        assert operator.status_code == 200
        assert operator.json()["role"] == "operator"


def test_persistent_revocation_lookup_failure_denies_access(tmp_path: Path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'missing.db'}")
    app = create_app(
        Settings(
            database_url=str(database.engine.url),
            api_viewer_token=VIEWER,
            api_persistent_revocation_enabled=True,
        ),
        database,
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/session", headers={"Authorization": f"Bearer {VIEWER}"})
        assert response.status_code == 503
        assert response.json()["detail"] == "persistent revocation check is unavailable"


@pytest.mark.asyncio
async def test_operator_revocation_workflow_is_audited_idempotent_and_immediate(
    tmp_path: Path,
) -> None:
    database = await configured_database(tmp_path / "operator.db", revoke_viewer=False)
    app = create_app(
        Settings(
            database_url=str(database.engine.url),
            api_viewer_token=VIEWER,
            api_operator_token=OPERATOR,
            api_persistent_revocation_enabled=True,
        ),
        database,
    )
    payload = {
        "token_sha256": sha256(VIEWER.encode()).hexdigest(),
        "reason": "credential exposed",
    }
    headers = {"Authorization": f"Bearer {OPERATOR}", "X-Correlation-ID": "incident-789"}
    with TestClient(app) as client:
        forbidden = client.post(
            "/api/v1/operator/token-revocations",
            json=payload,
            headers={"Authorization": f"Bearer {VIEWER}"},
        )
        assert forbidden.status_code == 403
        first = client.post("/api/v1/operator/token-revocations", json=payload, headers=headers)
        second = client.post("/api/v1/operator/token-revocations", json=payload, headers=headers)
        assert first.status_code == second.status_code == 201
        assert first.json()["id"] == second.json()["id"]
        revoked = client.get("/api/v1/session", headers={"Authorization": f"Bearer {VIEWER}"})
        assert revoked.status_code == 401
    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(RevokedAPITokenRecord)) == 1
        assert await session.scalar(select(func.count()).select_from(AuditEventRecord)) == 1
