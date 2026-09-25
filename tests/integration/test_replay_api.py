from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import sleep
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from packages.config import Settings
from packages.database import Base, Database

VIEWER = "viewer-token-that-is-at-least-32-characters"
OPERATOR = "operator-token-that-is-at-least-32-characters"
START = datetime(2026, 9, 24, 6, tzinfo=UTC)


def authorization(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def candle_payloads() -> list[dict[str, object]]:
    instrument_id = str(uuid4())
    return [
        {
            "instrument_id": instrument_id,
            "timestamp": (START + timedelta(minutes=index)).isoformat(),
            "timeframe_seconds": 60,
            "open": str(100 + index),
            "high": str(102 + index),
            "low": str(99 + index),
            "close": str(101 + index),
            "volume": "1000",
            "is_closed": True,
        }
        for index in range(3)
    ]


@pytest.mark.asyncio
async def test_authenticated_replay_api_enforces_roles_and_versions(tmp_path: Path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'replay-api.db'}")
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    app = create_app(
        Settings(
            database_url=str(database.engine.url),
            api_viewer_token=VIEWER,
            api_operator_token=OPERATOR,
        ),
        database,
    )
    session_id = str(uuid4())
    with TestClient(app) as client:
        denied = client.post(
            "/api/v1/operator/replay/datasets",
            json={"candles": candle_payloads()},
            headers=authorization(VIEWER),
        )
        assert denied.status_code == 403
        dataset = client.post(
            "/api/v1/operator/replay/datasets",
            json={"candles": candle_payloads()},
            headers=authorization(OPERATOR),
        )
        assert dataset.status_code == 201
        digest = dataset.json()["dataset_sha256"]
        created = client.post(
            "/api/v1/operator/replay/sessions",
            json={"session_id": session_id, "dataset_sha256": digest},
            headers=authorization(OPERATOR),
        )
        assert created.status_code == 201
        assert created.json()["version"] == created.json()["next_index"] == 0
        datasets = client.get("/api/v1/replay/datasets", headers=authorization(VIEWER))
        sessions = client.get("/api/v1/replay/sessions", headers=authorization(VIEWER))
        assert datasets.status_code == sessions.status_code == 200
        assert datasets.json()["items"][0]["dataset_sha256"] == digest
        assert sessions.json()["items"][0]["session_id"] == session_id
        assert client.get("/api/v1/replay/sessions").status_code == 401
        assert (
            client.get(
                "/api/v1/replay/datasets?limit=101", headers=authorization(VIEWER)
            ).status_code
            == 422
        )
        snapshot = client.get(
            f"/api/v1/replay/sessions/{session_id}", headers=authorization(VIEWER)
        )
        assert snapshot.status_code == 200
        assert snapshot.json()["candles"] == []
        forbidden_step = client.post(
            f"/api/v1/operator/replay/sessions/{session_id}/step",
            json={"expected_version": 0},
            headers=authorization(VIEWER),
        )
        assert forbidden_step.status_code == 403
        stepped = client.post(
            f"/api/v1/operator/replay/sessions/{session_id}/step",
            json={"expected_version": 0},
            headers=authorization(OPERATOR),
        )
        assert stepped.status_code == 200
        assert stepped.json()["version"] == stepped.json()["next_index"] == 1
        assert stepped.json()["frame"]["index"] == 0
        stale = client.post(
            f"/api/v1/operator/replay/sessions/{session_id}/step",
            json={"expected_version": 0},
            headers=authorization(OPERATOR),
        )
        assert stale.status_code == 409
        sought = client.post(
            f"/api/v1/operator/replay/sessions/{session_id}/seek",
            json={"expected_version": 1, "as_of": START.isoformat()},
            headers=authorization(OPERATOR),
        )
        assert sought.status_code == 200
        assert sought.json()["version"] == 2
        assert sought.json()["next_index"] == 0


@pytest.mark.asyncio
async def test_replay_api_returns_not_found_and_rejects_invalid_dataset(tmp_path: Path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'replay-errors.db'}")
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    app = create_app(
        Settings(database_url=str(database.engine.url), api_operator_token=OPERATOR), database
    )
    with TestClient(app) as client:
        missing = client.post(
            "/api/v1/operator/replay/sessions",
            json={"dataset_sha256": "0" * 64},
            headers=authorization(OPERATOR),
        )
        assert missing.status_code == 404
        invalid = client.post(
            "/api/v1/operator/replay/datasets",
            json={"candles": []},
            headers=authorization(OPERATOR),
        )
        assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_replay_playback_api_owns_and_reports_server_task(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'replay-playback.db'}"
    database = Database(database_url)
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    app = create_app(
        Settings(
            database_url=str(database.engine.url),
            api_viewer_token=VIEWER,
            api_operator_token=OPERATOR,
        ),
        database,
    )
    session_id = str(uuid4())
    with TestClient(app) as client:
        dataset = client.post(
            "/api/v1/operator/replay/datasets",
            json={"candles": candle_payloads()},
            headers=authorization(OPERATOR),
        ).json()
        client.post(
            "/api/v1/operator/replay/sessions",
            json={"session_id": session_id, "dataset_sha256": dataset["dataset_sha256"]},
            headers=authorization(OPERATOR),
        )
        path = f"/api/v1/operator/replay/sessions/{session_id}/playback"
        payload = {"expected_version": 0, "candles_per_second": 100, "maximum_steps": 3}
        assert client.post(path, json=payload, headers=authorization(VIEWER)).status_code == 403
        started = client.post(path, json=payload, headers=authorization(OPERATOR))
        assert started.status_code == 202
        assert started.json()["outcome"] == "running"
        assert started.json()["process_owned"] is True
        task_id = started.json()["task_id"]
        run_detail = client.get(
            f"/api/v1/replay/playback-runs/{task_id}", headers=authorization(VIEWER)
        )
        assert run_detail.status_code == 200
        assert run_detail.json()["task_id"] == task_id
        assert run_detail.json()["process_owned"] is (run_detail.json()["outcome"] == "running")
        assert client.post(path, json=payload, headers=authorization(OPERATOR)).status_code == 409

        status_path = f"/api/v1/replay/sessions/{session_id}/playback"
        for _ in range(50):
            playback = client.get(status_path, headers=authorization(VIEWER))
            if playback.json()["outcome"] != "running":
                break
            sleep(0.01)
        assert playback.status_code == 200
        assert playback.json()["outcome"] == "complete"
        assert playback.json()["frames_emitted"] == 3
        assert playback.json()["resulting_version"] == 3
        assert playback.json()["process_owned"] is False
        client.post(f"{path}/stop", headers=authorization(OPERATOR))
        history = client.get(
            f"/api/v1/replay/sessions/{session_id}/playback-runs",
            headers=authorization(VIEWER),
        )
        assert history.status_code == 200
        assert history.json()["items"][0]["task_id"] == started.json()["task_id"]
        assert history.json()["items"][0]["outcome"] == "complete"
        stopped_session_id = str(uuid4())
        client.post(
            "/api/v1/operator/replay/sessions",
            json={
                "session_id": stopped_session_id,
                "dataset_sha256": dataset["dataset_sha256"],
            },
            headers=authorization(OPERATOR),
        )
        stopped_path = f"/api/v1/operator/replay/sessions/{stopped_session_id}/playback"
        client.post(
            stopped_path,
            json={"expected_version": 0, "candles_per_second": 0.1, "maximum_steps": 3},
            headers=authorization(OPERATOR),
        )
        stop_path = f"{stopped_path}/stop"
        assert client.post(stop_path, headers=authorization(VIEWER)).status_code == 403
        stopped = client.post(stop_path, headers=authorization(OPERATOR))
        assert stopped.status_code == 200
        assert stopped.json()["outcome"] == "stopped"
        assert (
            client.get(
                f"/api/v1/replay/sessions/{uuid4()}/playback",
                headers=authorization(VIEWER),
            ).status_code
            == 404
        )

    restarted_database = Database(database_url)
    restarted_app = create_app(
        Settings(
            database_url=database_url,
            api_viewer_token=VIEWER,
            api_operator_token=OPERATOR,
        ),
        restarted_database,
    )
    with TestClient(restarted_app) as restarted_client:
        recovered = restarted_client.get(status_path, headers=authorization(VIEWER))
        assert recovered.status_code == 200
        assert recovered.json()["task_id"] == started.json()["task_id"]
        assert recovered.json()["outcome"] == "complete"
        assert recovered.json()["process_owned"] is False
        recovered_detail = restarted_client.get(
            f"/api/v1/replay/playback-runs/{task_id}", headers=authorization(VIEWER)
        )
        assert recovered_detail.status_code == 200
        assert recovered_detail.json()["outcome"] == "complete"
        assert recovered_detail.json()["process_owned"] is False
        assert (
            restarted_client.get(
                f"/api/v1/replay/playback-runs/{uuid4()}", headers=authorization(VIEWER)
            ).status_code
            == 404
        )
        assert (
            restarted_client.post(f"{path}/stop", headers=authorization(OPERATOR)).status_code
            == 409
        )
        assert (
            restarted_client.post(
                f"/api/v1/operator/replay/sessions/{uuid4()}/playback",
                json=payload,
                headers=authorization(OPERATOR),
            ).status_code
            == 404
        )
