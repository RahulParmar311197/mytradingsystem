from fastapi.testclient import TestClient

from apps.api.main import create_app
from packages.config import Settings


def test_replay_console_serves_hardened_responsive_assets() -> None:
    with TestClient(create_app(Settings(database_url="sqlite+aiosqlite:///:memory:"))) as client:
        page = client.get("/replay")
        assert page.status_code == 200
        assert "Market replay" in page.text
        assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
        assert page.headers["cache-control"] == "no-store"
        stylesheet = client.get("/assets/replay.css")
        script = client.get("/assets/replay.js")
        assert stylesheet.status_code == script.status_code == 200
        assert "@media (max-width: 760px)" in stylesheet.text
        assert "sessionStorage" in script.text
        assert "localStorage" not in script.text
        assert 'id="candleChart"' in page.text
        assert "createElementNS" in script.text
        assert "sourceRows.slice(-100)" in script.text
        assert 'id="datasetForm"' in page.text
        assert "MAX_DATASET_BYTES" in script.text
        assert "crypto.randomUUID()" in script.text
        assert "/api/v1/operator/replay/datasets" in script.text
        assert 'id="recentSessions"' in page.text
        assert "/api/v1/replay/sessions?limit=25" in script.text
        assert "select.replaceChildren()" in script.text
        assert 'id="playbackRate"' in page.text
        assert 'id="play"' in page.text
        assert "startServerPlayback" in script.text
        assert "/playback/stop" in script.text
        assert "stopped before disconnecting" in script.text
        assert "Previous server playback stopped" in script.text
        assert "if (!(await stopServerPlayback" in script.text
        assert "playbackPending" in script.text
        assert "const playbackBusy = state.playing || state.playbackPending" in script.text
        assert "Playback started, but run history is unavailable" in script.text
        assert "Playback stopped, but the prefix refresh failed" in script.text
        assert "playbackPollFailures" in script.text
        assert "Playback ownership is retained; status polling will retry" in script.text
        assert "Playback is running, but the prefix refresh failed" in script.text
        assert "pollServerPlayback" in script.text
        assert 'id="playbackStatus"' in page.text
        assert 'id="playbackHistory"' in page.text
        assert 'id="refreshPlaybackHistory"' in page.text
        assert "/playback-runs?limit=10" in script.text
        assert "run.task_id.slice(0, 8)" in script.text
        assert 'document.addEventListener("visibilitychange"' in script.text
