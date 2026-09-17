from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from apps.api.main import create_app
from packages.config.settings import Settings


class FakeDatabase:
    def __init__(self, ready: bool) -> None:
        self.ready = ready

    async def is_ready(self) -> bool:
        return self.ready

    async def close(self) -> None:
        return None

    async def session(self) -> AsyncIterator[None]:
        yield None


def test_liveness_exposes_paper_mode_and_security_headers() -> None:
    app = create_app(Settings(_env_file=None), FakeDatabase(True))  # type: ignore[arg-type]
    with TestClient(app) as client:
        response = client.get("/health/live", headers={"X-Correlation-ID": "test-correlation"})
    assert response.status_code == 200
    assert response.json() == {"status": "alive", "trading_mode": "paper"}
    assert response.headers["x-correlation-id"] == "test-correlation"
    assert response.headers["x-frame-options"] == "DENY"


def test_readiness_fails_when_database_is_unavailable() -> None:
    app = create_app(Settings(_env_file=None), FakeDatabase(False))  # type: ignore[arg-type]
    with TestClient(app) as client:
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["checks"] == {"database": False}
