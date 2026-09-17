from enum import StrEnum
from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TradingMode(StrEnum):
    PAPER = "paper"
    LIVE = "live"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MTS_", env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql+asyncpg://mts_app:change_me@localhost:5432/mts"
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    trading_mode: TradingMode = TradingMode.PAPER
    live_trading_enabled: bool = False
    live_trading_confirmation: SecretStr | None = None
    broker_authenticated: bool = False
    risk_limits_configured: bool = False
    paper_validation_passed: bool = False
    market_data_healthy: bool = False
    broker_reconciled: bool = False
    audit_logging_enabled: bool = True
    kill_switch_enabled: bool = True

    @model_validator(mode="after")
    def enforce_live_interlocks(self) -> "Settings":
        if self.trading_mode is TradingMode.PAPER:
            return self
        checks = {
            "live_trading_enabled": self.live_trading_enabled,
            "broker_authenticated": self.broker_authenticated,
            "risk_limits_configured": self.risk_limits_configured,
            "paper_validation_passed": self.paper_validation_passed,
            "market_data_healthy": self.market_data_healthy,
            "broker_reconciled": self.broker_reconciled,
            "audit_logging_enabled": self.audit_logging_enabled,
            "kill_switch_enabled": self.kill_switch_enabled,
            "explicit_confirmation": self.live_trading_confirmation is not None
            and self.live_trading_confirmation.get_secret_value() == "I_CONFIRM_LIVE_TRADING",
        }
        missing = sorted(name for name, passed in checks.items() if not passed)
        if missing:
            raise ValueError(f"live trading safety interlocks not satisfied: {', '.join(missing)}")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
