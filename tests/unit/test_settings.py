import pytest
from pydantic import ValidationError

from packages.config.settings import Settings, TradingMode


def test_live_trading_is_disabled_by_default() -> None:
    settings = Settings(_env_file=None)
    assert settings.trading_mode is TradingMode.PAPER
    assert settings.live_trading_enabled is False


def test_live_mode_fails_closed_without_every_interlock() -> None:
    with pytest.raises(ValidationError, match="live trading safety interlocks"):
        Settings(_env_file=None, trading_mode="live", live_trading_enabled=True)


def test_live_mode_requires_exact_explicit_confirmation() -> None:
    common = dict(
        trading_mode="live",
        live_trading_enabled=True,
        broker_authenticated=True,
        risk_limits_configured=True,
        paper_validation_passed=True,
        market_data_healthy=True,
        broker_reconciled=True,
        audit_logging_enabled=True,
        kill_switch_enabled=True,
    )
    with pytest.raises(ValidationError, match="explicit_confirmation"):
        Settings(_env_file=None, live_trading_confirmation="yes", **common)
    settings = Settings(
        _env_file=None, live_trading_confirmation="I_CONFIRM_LIVE_TRADING", **common
    )
    assert settings.trading_mode is TradingMode.LIVE
