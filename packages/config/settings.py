from datetime import datetime
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
    api_viewer_token: SecretStr | None = None
    api_operator_token: SecretStr | None = None
    api_previous_viewer_token: SecretStr | None = None
    api_previous_operator_token: SecretStr | None = None
    api_previous_tokens_expire_at: datetime | None = None
    api_revoked_token_sha256: list[str] = Field(default_factory=list)
    api_persistent_revocation_enabled: bool = False

    @model_validator(mode="after")
    def enforce_live_interlocks(self) -> "Settings":
        configured_tokens = tuple(
            token.get_secret_value()
            for token in (
                self.api_viewer_token,
                self.api_operator_token,
                self.api_previous_viewer_token,
                self.api_previous_operator_token,
            )
            if token is not None
        )
        if any(len(token) < 32 for token in configured_tokens):
            raise ValueError("API bearer tokens must contain at least 32 characters")
        if len(configured_tokens) != len(set(configured_tokens)):
            raise ValueError("API bearer tokens must be distinct")
        previous_configured = any(
            token is not None
            for token in (self.api_previous_viewer_token, self.api_previous_operator_token)
        )
        if previous_configured and self.api_previous_tokens_expire_at is None:
            raise ValueError("previous API tokens require an expiry")
        if self.api_previous_tokens_expire_at is not None and (
            self.api_previous_tokens_expire_at.tzinfo is None
            or self.api_previous_tokens_expire_at.utcoffset() is None
        ):
            raise ValueError("previous API token expiry must be timezone-aware")
        if len(self.api_revoked_token_sha256) != len(set(self.api_revoked_token_sha256)) or any(
            len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest)
            for digest in self.api_revoked_token_sha256
        ):
            raise ValueError("revoked API token digests must be unique lowercase SHA-256 values")
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
