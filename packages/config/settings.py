from enum import StrEnum
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TradingMode(StrEnum):
    PAPER = "paper"
    LIVE = "live"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MTS_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = Field(default="postgresql+asyncpg://localhost:5432/mts", repr=False)
    redis_url: str = Field(default="redis://localhost:6379/0", repr=False)
    redis_required: bool = False
    dependency_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    otel_endpoint: str | None = None
    worker_interval_seconds: float = Field(default=5, ge=1, le=60)
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
        if "*" in self.cors_origins:
            raise ValueError("CORS requires an explicit origin allowlist")
        for origin in self.cors_origins:
            parsed = urlsplit(origin)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path:
                raise ValueError("CORS origins must be HTTP(S) origins without paths")
        if self.environment == "production":
            if not self.database_url.startswith("postgresql+asyncpg://"):
                raise ValueError("production requires PostgreSQL")
            if not self.redis_required:
                raise ValueError("production requires Redis readiness checks")
            if any(not origin.startswith("https://") for origin in self.cors_origins):
                raise ValueError("production CORS origins require HTTPS")
            if "change_me" in self.database_url or "REPLACE_" in self.database_url:
                raise ValueError("production database credentials must be configured")
        if self.trading_mode is TradingMode.PAPER:
            if self.live_trading_enabled:
                raise ValueError("paper mode cannot enable live trading")
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
