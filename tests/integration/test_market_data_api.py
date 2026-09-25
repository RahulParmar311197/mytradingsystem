"""Real SQLite API cycle: instrument -> raw validation -> causal candles."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

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
        conflicting_feed = client.post(
            "/api/v1/operator/market-data/candles",
            json={
                "source": "other-feed",
                "candles": [
                    {**candle(instrument_id, 0), "source_event_id": "other-0", "close": "100.5"}
                ],
            },
            headers=auth(OPERATOR),
        )
        assert conflicting_feed.status_code == 201
        assert conflicting_feed.json() == {
            "raw_inserted": 1,
            "normalized_inserted": 0,
            "quality_events_recorded": 1,
        }

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
        codes = [
            item["code"]
            for item in client.get(
                f"/api/v1/instruments/{instrument_id}/quality-events", headers=auth(VIEWER)
            ).json()["items"]
        ]
        assert "CONFLICTING_CANDLE" in codes
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


@pytest.mark.asyncio
async def test_published_short_session_is_used_for_api_intraday_aggregation(tmp_path: Path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'special-session.db'}")
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
    opening = datetime(2026, 9, 24, 18, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    with TestClient(app) as client:
        instrument = {
            "id": instrument_id,
            "symbol": "SPECIAL",
            "exchange": "NSE",
            "segment": "CASH",
            "tick_size": "0.05",
            "lot_size": 1,
        }
        assert client.post(
            "/api/v1/operator/instruments",
            json={"instruments": [instrument]},
            headers=auth(OPERATOR),
        ).status_code == 201
        published_at = datetime(2026, 9, 23, tzinfo=UTC)
        calendar = {
            "source": "reviewed-special-session",
            "published_at": published_at.isoformat(),
            "sessions": [{
                "exchange": "NSE",
                "session_date": "2026-09-24",
                "opens_at": opening.isoformat(),
                "closes_at": (opening + timedelta(minutes=12)).isoformat(),
                "is_trading_day": True,
            }],
        }
        assert client.post(
            "/api/v1/operator/calendars/nse/sessions", json=calendar, headers=auth(OPERATOR)
        ).status_code == 201
        bars = [
            {
                **candle(instrument_id, index),
                "timestamp": (opening + timedelta(minutes=index)).isoformat(),
                "source_event_id": f"special-{index}",
            }
            for index in range(12)
        ]
        imported = client.post(
            "/api/v1/operator/market-data/candles",
            json={"source": "special-feed", "candles": bars},
            headers=auth(OPERATOR),
        )
        assert imported.status_code == 201, imported.text
        assert imported.json()["normalized_inserted"] == 12
        query = {
            "start": opening.isoformat(),
            "end": (opening + timedelta(minutes=13)).isoformat(),
            "as_of": (opening + timedelta(minutes=12)).isoformat(),
            "timeframe_seconds": 60,
            "aggregate_seconds": 300,
        }
        path = f"/api/v1/instruments/{instrument_id}/candles"
        response = client.get(path, params=query, headers=auth(VIEWER))
        assert response.status_code == 200, response.text
        assert [Decimal(item["volume"]) for item in response.json()["items"]] == [
            Decimal(500),
            Decimal(500),
            Decimal(200),
        ]
    await database.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("published_at", ["2026-09-13T00:00:00Z", "2026-09-18T00:00:00Z"])
async def test_holiday_week_requires_published_calendar_and_persists_across_restart(
    tmp_path: Path,
    published_at: str,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'calendar.db'}"
    database = Database(database_url)
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    settings = Settings(
        database_url=database_url, api_viewer_token=VIEWER, api_operator_token=OPERATOR
    )
    instrument_id = str(uuid4())
    local = ZoneInfo("Asia/Kolkata")
    monday = datetime(2026, 9, 14, 9, 15, tzinfo=local)
    sessions = [
        {
            "exchange": "NSE",
            "session_date": (monday + timedelta(days=day)).date().isoformat(),
            "opens_at": (monday + timedelta(days=day)).isoformat(),
            "closes_at": (monday + timedelta(days=day, hours=6, minutes=15)).isoformat(),
            "is_trading_day": day != 4,
        }
        for day in range(5)
    ]
    with TestClient(create_app(settings, database)) as client:
        imported = client.post(
            "/api/v1/operator/instruments",
            json={
                "instruments": [
                    {
                        "id": instrument_id,
                        "symbol": "NIFTY 50",
                        "exchange": "NSE",
                        "segment": "CASH",
                        "tick_size": "0.05",
                        "lot_size": 1,
                    }
                ]
            },
            headers=auth(OPERATOR),
        )
        assert imported.status_code == 201
        bars = [
            {
                **candle(instrument_id, 0),
                "timestamp": (monday + timedelta(days=day)).isoformat(),
                "timeframe_seconds": 86400,
                "source_event_id": f"daily-{day}",
            }
            for day in range(4)
        ]
        assert (
            client.post(
                "/api/v1/operator/market-data/candles",
                json={
                    "source": "licensed-historical",
                    "candles": bars,
                },
                headers=auth(OPERATOR),
            ).json()["normalized_inserted"]
            == 4
        )
        query = {
            "start": monday.isoformat(),
            "end": (monday + timedelta(days=5)).isoformat(),
            "timeframe_seconds": 86400,
            "aggregate_seconds": 604800,
            "as_of": sessions[3]["closes_at"],
        }
        path = f"/api/v1/instruments/{instrument_id}/candles"
        assert client.get(path, params=query, headers=auth(VIEWER)).status_code == 409
        calendar_path = "/api/v1/operator/calendars/nse/sessions"
        payload = {
            "source": "owner-reviewed-calendar",
            "published_at": published_at,
            "sessions": sessions,
        }
        assert client.post(calendar_path, json=payload, headers=auth(VIEWER)).status_code == 403
        assert client.post(calendar_path, json=payload, headers=auth(OPERATOR)).json() == {
            "inserted": 5
        }
        assert client.post(calendar_path, json=payload, headers=auth(OPERATOR)).json() == {
            "inserted": 0
        }
        assert (
            client.post(
                calendar_path,
                json={**payload, "sessions": [{**sessions[4], "is_trading_day": True}]},
                headers=auth(OPERATOR),
            ).status_code
            == 409
        )
        before = client.get(
            path, params={**query, "as_of": "2026-09-17T09:59:59Z"}, headers=auth(VIEWER)
        )
        if published_at.startswith("2026-09-13"):
            assert before.status_code == 200 and before.json()["items"] == []
        else:
            assert before.status_code == 409
        complete = client.get(path, params=query, headers=auth(VIEWER))
        if published_at.startswith("2026-09-18"):
            assert complete.status_code == 409
            query["as_of"] = published_at
            complete = client.get(path, params=query, headers=auth(VIEWER))
        assert complete.status_code == 200 and len(complete.json()["items"]) == 1
        assert complete.json()["items"][0]["volume"] == "400.00000000"
    restored = Database(database_url)
    with TestClient(create_app(settings, restored)) as client:
        assert len(client.get(path, params=query, headers=auth(VIEWER)).json()["items"]) == 1
