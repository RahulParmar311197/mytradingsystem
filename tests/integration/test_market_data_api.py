"""Real SQLite API cycle: instrument -> raw validation -> causal candles."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from packages.config import Settings
from packages.database import Base, Database

VIEWER = "market-viewer-token-at-least-32-characters"
OPERATOR = "market-operator-token-at-least-32-characters"
START = datetime(2026, 9, 24, 3, 45, tzinfo=UTC)


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def candle(instrument_id: str, index: int, *, bad: bool = False) -> dict[str, object]:
    return {
        "instrument_id": instrument_id,
        "timestamp": (START + timedelta(minutes=index)).isoformat(),
        "timeframe_seconds": 60,
        "open": "100",
        "high": "99" if bad else "102",
        "low": "98",
        "close": "101",
        "volume": "100",
        "source_event_id": f"feed-{index}",
    }


@pytest.mark.asyncio
async def test_historical_ingestion_validation_roles_and_point_in_time_read(tmp_path: Path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'market-data.db'}")
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
    instrument_id = str(uuid4())
    instrument = {
        "id": instrument_id,
        "symbol": "NIFTY 50",
        "exchange": "NSE",
        "segment": "CASH",
        "tick_size": "0.05",
        "lot_size": 1,
    }
    with TestClient(app) as client:
        assert client.get("/api/v1/instruments").status_code == 401
        assert (
            client.post(
                "/api/v1/operator/instruments",
                json={"instruments": [instrument]},
                headers=auth(VIEWER),
            ).status_code
            == 403
        )
        created = client.post(
            "/api/v1/operator/instruments",
            json={"instruments": [instrument]},
            headers=auth(OPERATOR),
        )
        assert created.status_code == 201
        assert created.json() == {"inserted": 1}
        conflict = client.post(
            "/api/v1/operator/instruments",
            json={"instruments": [{**instrument, "id": str(uuid4())}]},
            headers=auth(OPERATOR),
        )
        assert conflict.status_code == 409
        changed_lot = client.post(
            "/api/v1/operator/instruments",
            json={"instruments": [{**instrument, "lot_size": 25}]},
            headers=auth(OPERATOR),
        )
        assert changed_lot.status_code == 409
        assert (
            client.get("/api/v1/instruments", headers=auth(VIEWER)).json()["items"][0]["id"]
            == instrument_id
        )

        payload = {"source": "test-feed", "candles": [candle(instrument_id, n) for n in range(5)]}
        payload["candles"].append(candle(instrument_id, 5, bad=True))
        assert (
            client.post(
                "/api/v1/operator/market-data/candles", json=payload, headers=auth(VIEWER)
            ).status_code
            == 403
        )
        imported = client.post(
            "/api/v1/operator/market-data/candles", json=payload, headers=auth(OPERATOR)
        )
        assert imported.status_code == 201, imported.text
        assert imported.json() == {
            "raw_inserted": 6,
            "normalized_inserted": 5,
            "quality_events_recorded": 1,
        }
        repeated = client.post(
            "/api/v1/operator/market-data/candles", json=payload, headers=auth(OPERATOR)
        )
        assert repeated.status_code == 201
        assert repeated.json() == {
            "raw_inserted": 0,
            "normalized_inserted": 0,
            "quality_events_recorded": 0,
        }
        reused = client.post(
            "/api/v1/operator/market-data/candles",
            json={
                "source": "test-feed",
                "candles": [{**candle(instrument_id, 0), "volume": "999"}],
            },
            headers=auth(OPERATOR),
        )
        assert reused.status_code == 409

        path = f"/api/v1/instruments/{instrument_id}/candles"
        query = {
            "start": START.isoformat(),
            "end": (START + timedelta(minutes=6)).isoformat(),
            "as_of": (START + timedelta(minutes=4)).isoformat(),
            "aggregate_seconds": 300,
        }
        early = client.get(path, params=query, headers=auth(VIEWER))
        assert early.status_code == 200, early.text
        assert early.json()["items"] == []
        query["as_of"] = (START + timedelta(minutes=5)).isoformat()
        complete = client.get(path, params=query, headers=auth(VIEWER))
        assert complete.status_code == 200
        assert len(complete.json()["items"]) == 1
        assert complete.json()["items"][0]["volume"] == "500.00000000"
        assert complete.json()["data_type"] == "historical"
        assert (
            client.get(
                f"/api/v1/instruments/{instrument_id}/quality-events", headers=auth(VIEWER)
            ).json()["items"][0]["code"]
            == "INVALID_CANDLE"
        )
        assert (
            client.get(
                path, params={**query, "as_of": "2026-09-24T09:20:00"}, headers=auth(VIEWER)
            ).status_code
            == 422
        )


@pytest.mark.asyncio
async def test_unknown_instrument_rejected_before_ingestion(tmp_path: Path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'empty.db'}")
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    app = create_app(
        Settings(database_url=str(database.engine.url), api_operator_token=OPERATOR), database
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/operator/market-data/candles",
            json={"source": "test-feed", "candles": [candle(str(uuid4()), 0)]},
            headers=auth(OPERATOR),
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_daily_candle_visible_at_nse_session_close(tmp_path: Path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'daily.db'}")
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
    instrument_id = str(uuid4())
    with TestClient(app) as client:
        client.post(
            "/api/v1/operator/instruments",
            json={
                "instruments": [
                    {
                        "id": instrument_id,
                        "symbol": "BANKNIFTY",
                        "exchange": "NSE",
                        "segment": "CASH",
                        "tick_size": "0.05",
                        "lot_size": 1,
                    }
                ]
            },
            headers=auth(OPERATOR),
        )
        daily = candle(instrument_id, 0)
        daily["timeframe_seconds"] = 86400
        client.post(
            "/api/v1/operator/market-data/candles",
            json={"source": "test-feed", "candles": [daily]},
            headers=auth(OPERATOR),
        )
        query = {
            "start": START.isoformat(),
            "end": (START + timedelta(days=1)).isoformat(),
            "timeframe_seconds": 86400,
            "as_of": "2026-09-24T09:59:59+00:00",
        }
        path = f"/api/v1/instruments/{instrument_id}/candles"
        assert client.get(path, params=query, headers=auth(VIEWER)).json()["items"] == []
        query["as_of"] = "2026-09-24T10:00:00+00:00"
        assert len(client.get(path, params=query, headers=auth(VIEWER)).json()["items"]) == 1
