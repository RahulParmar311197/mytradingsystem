import json
import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from apps.api.main import create_app
from packages.config import Settings
from packages.observability.logging import RedactionFilter, SafeJsonFormatter, safe_context


@pytest.mark.parametrize(
    "value", ["access_token=topsecret", "Bearer topsecret", "postgresql://user:topsecret@db/app"]
)
def test_interpolated_secrets_are_redacted(value: str) -> None:
    record = logging.makeLogRecord(
        {"msg": "failure: %s", "args": (value,), "nested": {"refresh_token": "topsecret"}}
    )
    RedactionFilter().filter(record)
    formatted = SafeJsonFormatter().format(record)
    assert "topsecret" not in formatted
    assert "[REDACTED]" in formatted
    json.loads(formatted)


def test_nested_secrets_and_secret_types_are_redacted() -> None:
    context = safe_context(
        {
            "broker": [{"authorization": "hidden", "config": {"api_key": "hidden"}}],
            "value": SecretStr("hidden"),
        }
    )
    assert "hidden" not in json.dumps(context)


def test_live_api_is_unavailable_even_if_configuration_claims_all_checks_passed() -> None:
    settings = Settings(
        _env_file=None,
        trading_mode="live",
        live_trading_enabled=True,
        live_trading_confirmation="I_CONFIRM_LIVE_TRADING",
        broker_authenticated=True,
        risk_limits_configured=True,
        paper_validation_passed=True,
        market_data_healthy=True,
        broker_reconciled=True,
        audit_logging_enabled=True,
        kill_switch_enabled=True,
    )
    with pytest.raises(RuntimeError, match="live execution is unavailable"):
        create_app(settings)


def test_configuration_rejects_inconsistent_mode_and_wildcard_cors() -> None:
    with pytest.raises(ValidationError, match="paper mode"):
        Settings(_env_file=None, live_trading_enabled=True)
    with pytest.raises(ValidationError, match="allowlist"):
        Settings(_env_file=None, cors_origins=["*"])


def test_route_metrics_do_not_label_arbitrary_paths(migrated_url: str) -> None:
    with TestClient(create_app(Settings(_env_file=None, database_url=migrated_url))) as client:
        for path in ("/random-sensitive-123", "/random-sensitive-456"):
            response = client.get(path, headers={"X-Correlation-ID": "password=hidden"})
            assert response.status_code == 404
            assert response.headers["X-Correlation-ID"] != "password=hidden"
        metrics = client.get("/metrics").text
        assert "random-sensitive" not in metrics
        assert 'path="unmatched"' in metrics


def test_redis_outage_fails_readiness(migrated_url: str) -> None:
    settings = Settings(
        _env_file=None,
        database_url=migrated_url,
        redis_required=True,
        redis_url="redis://127.0.0.1:1/0",
        dependency_timeout_seconds=0.1,
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["checks"] == {"database": True, "redis": False}
