from datetime import UTC, datetime, timedelta
from hashlib import sha256

from fastapi.testclient import TestClient

from apps.api.main import create_app
from packages.config import Settings

VIEWER = "viewer-token-that-is-at-least-32-characters"
OPERATOR = "operator-token-that-is-at-least-32-characters"
PREVIOUS = "previous-token-that-is-at-least-32-characters"


def client(**settings: object) -> TestClient:
    return TestClient(
        create_app(
            Settings(
                database_url="sqlite+aiosqlite:///:memory:",
                api_viewer_token=VIEWER,
                api_operator_token=OPERATOR,
                **settings,
            )
        )
    )


def test_protected_session_requires_bearer_authentication() -> None:
    api = client()
    response = api.get("/api/v1/session")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    response = api.get("/api/v1/session", headers={"Authorization": f"Bearer {VIEWER}"})
    assert response.status_code == 200
    assert response.json() == {
        "subject": "api:viewer",
        "role": "viewer",
        "trading_mode": "paper",
    }


def test_operator_route_enforces_role_without_changing_mode() -> None:
    api = client()
    viewer = api.get("/api/v1/operator/mode", headers={"Authorization": f"Bearer {VIEWER}"})
    assert viewer.status_code == 403
    operator = api.get("/api/v1/operator/mode", headers={"Authorization": f"Bearer {OPERATOR}"})
    assert operator.status_code == 200
    assert operator.json()["trading_mode"] == "paper"


def test_protected_routes_fail_closed_without_authentication_configuration() -> None:
    api = TestClient(create_app(Settings(database_url="sqlite+aiosqlite:///:memory:")))
    response = api.get("/api/v1/session", headers={"Authorization": f"Bearer {VIEWER}"})
    assert response.status_code == 503


def test_api_accepts_previous_token_during_explicit_rotation_window() -> None:
    api = client(
        api_previous_viewer_token=PREVIOUS,
        api_previous_tokens_expire_at=datetime.now(UTC) + timedelta(hours=1),
    )
    response = api.get("/api/v1/session", headers={"Authorization": f"Bearer {PREVIOUS}"})
    assert response.status_code == 200
    assert response.json()["role"] == "viewer"


def test_api_rejects_configured_revoked_token_without_disabling_other_roles() -> None:
    api = client(api_revoked_token_sha256=[sha256(VIEWER.encode()).hexdigest()])
    revoked = api.get("/api/v1/session", headers={"Authorization": f"Bearer {VIEWER}"})
    assert revoked.status_code == 401
    operator = api.get("/api/v1/session", headers={"Authorization": f"Bearer {OPERATOR}"})
    assert operator.status_code == 200
    assert operator.json()["role"] == "operator"
