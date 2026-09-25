"""Durable idempotent persistence boundary for final risk decisions."""

import json
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models import (
    AuditEventRecord,
    RiskDecisionRecord,
    RiskLimitRecord,
    SafetyStateRecord,
)
from packages.domain.models import OrderIntent, RiskDecision, RiskOutcome
from packages.risk_engine.engine import (
    PortfolioRiskContext,
    RiskEvaluationRequest,
    RiskLimits,
    evaluate_order_risk,
)


class RiskLimitType(StrEnum):
    MAXIMUM_RISK_PER_TRADE_FRACTION = "maximum_risk_per_trade_fraction"
    MAXIMUM_DAILY_LOSS_FRACTION = "maximum_daily_loss_fraction"
    MAXIMUM_OPEN_POSITIONS = "maximum_open_positions"
    MAXIMUM_INSTRUMENT_EXPOSURE_FRACTION = "maximum_instrument_exposure_fraction"
    MAXIMUM_QUOTE_AGE_SECONDS = "maximum_quote_age_seconds"
    MAXIMUM_SPREAD_BPS = "maximum_spread_bps"
    MAXIMUM_WEEKLY_LOSS_FRACTION = "maximum_weekly_loss_fraction"
    MAXIMUM_DRAWDOWN_FRACTION = "maximum_drawdown_fraction"
    MAXIMUM_GROSS_EXPOSURE_FRACTION = "maximum_gross_exposure_fraction"
    MAXIMUM_NET_EXPOSURE_FRACTION = "maximum_net_exposure_fraction"
    MAXIMUM_ORDERS_PER_MINUTE = "maximum_orders_per_minute"
    MAXIMUM_CONSECUTIVE_LOSSES = "maximum_consecutive_losses"
    MAXIMUM_SECTOR_EXPOSURE_FRACTION = "maximum_sector_exposure_fraction"
    MAXIMUM_STRATEGY_ALLOCATION_FRACTION = "maximum_strategy_allocation_fraction"
    MAXIMUM_SLIPPAGE_BPS = "maximum_slippage_bps"
    MAXIMUM_OPTIONS_EXPOSURE = "maximum_options_exposure"
    MAXIMUM_PORTFOLIO_DELTA = "maximum_portfolio_delta"
    MAXIMUM_PORTFOLIO_GAMMA = "maximum_portfolio_gamma"


@dataclass(frozen=True, slots=True)
class PersistedRiskConfiguration:
    limits: RiskLimits
    kill_switch_enabled: bool
    kill_switch_reason: str


def _fingerprint(request: RiskEvaluationRequest) -> str:
    payload = {
        "intent": request.intent.model_dump(mode="json"),
        "context": asdict(request.context),
        "limits": asdict(request.limits),
        "reference_price": request.reference_price,
        "stop_price": request.stop_price,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return sha256(encoded).hexdigest()


def _aware(timestamp: datetime) -> datetime:
    return timestamp.replace(tzinfo=UTC) if timestamp.tzinfo is None else timestamp.astimezone(UTC)


class PersistentRiskAuthority:
    """Evaluate once per intent and retain the complete final decision across restarts."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def evaluate(self, request: RiskEvaluationRequest) -> RiskDecision:
        fingerprint = _fingerprint(request)
        existing = await self.session.scalar(
            select(RiskDecisionRecord).where(
                RiskDecisionRecord.order_intent_id == request.intent.id
            )
        )
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise ValueError("order intent already has a decision for different risk inputs")
            return self._domain(existing)

        decision = evaluate_order_risk(request)
        record = RiskDecisionRecord(
            id=decision.id,
            order_intent_id=decision.order_intent_id,
            account_id=request.intent.account_id,
            instrument_id=request.intent.instrument_id,
            evaluated_at=decision.timestamp,
            outcome=decision.outcome.value,
            approved_quantity=decision.approved_quantity,
            reason_codes=list(decision.reason_codes),
            policy_version=decision.risk_policy_version,
            request_fingerprint=fingerprint,
        )
        self.session.add(record)
        await self.session.flush()
        return decision

    async def evaluate_with_persisted_configuration(
        self,
        intent: OrderIntent,
        context: PortfolioRiskContext,
        reference_price: Decimal,
        stop_price: Decimal | None,
    ) -> RiskDecision:
        """Load effective controls, force persisted kill state, evaluate, and persist atomically."""
        configuration = await PersistentRiskConfigurationStore(self.session).load(
            intent.account_id, context.evaluated_at
        )
        effective_context = replace(
            context,
            kill_switch_enabled=(context.kill_switch_enabled or configuration.kill_switch_enabled),
        )
        return await self.evaluate(
            RiskEvaluationRequest(
                intent,
                effective_context,
                configuration.limits,
                reference_price,
                stop_price,
            )
        )

    @staticmethod
    def _domain(record: RiskDecisionRecord) -> RiskDecision:
        return RiskDecision(
            id=record.id,
            order_intent_id=record.order_intent_id,
            timestamp=_aware(record.evaluated_at),
            outcome=RiskOutcome(record.outcome),
            approved_quantity=record.approved_quantity,
            reason_codes=tuple(record.reason_codes),
            risk_policy_version=record.policy_version,
        )


class PersistentRiskConfigurationStore:
    """Load effective limits and operate the durable manual kill switch."""

    KILL_SWITCH_KEY = "kill_switch"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def load(self, account_id: UUID, as_of: datetime) -> PersistedRiskConfiguration:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("risk configuration timestamp must be timezone-aware")
        as_of = as_of.astimezone(UTC)
        records = tuple(
            (
                await self.session.scalars(
                    select(RiskLimitRecord)
                    .where(
                        RiskLimitRecord.account_id == account_id,
                        RiskLimitRecord.enabled.is_(True),
                        RiskLimitRecord.effective_from <= as_of,
                    )
                    .order_by(RiskLimitRecord.effective_from.desc())
                )
            ).all()
        )
        latest: dict[str, RiskLimitRecord] = {}
        for record in records:
            latest.setdefault(record.limit_type, record)
        missing = sorted(item.value for item in RiskLimitType if item.value not in latest)
        if missing:
            raise RuntimeError(f"missing effective risk limits: {', '.join(missing)}")
        version_material = "|".join(
            f"{item.value}:{latest[item.value].id}:{latest[item.value].value}:"
            f"{latest[item.value].effective_from.isoformat()}"
            for item in RiskLimitType
        )
        version = f"persisted-{sha256(version_material.encode()).hexdigest()[:16]}"
        limits = RiskLimits(
            version,
            latest[RiskLimitType.MAXIMUM_RISK_PER_TRADE_FRACTION].value,
            latest[RiskLimitType.MAXIMUM_DAILY_LOSS_FRACTION].value,
            self._whole_number(
                latest[RiskLimitType.MAXIMUM_OPEN_POSITIONS].value, "open positions"
            ),
            latest[RiskLimitType.MAXIMUM_INSTRUMENT_EXPOSURE_FRACTION].value,
            self._whole_number(latest[RiskLimitType.MAXIMUM_QUOTE_AGE_SECONDS].value, "quote age"),
            latest[RiskLimitType.MAXIMUM_SPREAD_BPS].value,
            latest[RiskLimitType.MAXIMUM_WEEKLY_LOSS_FRACTION].value,
            latest[RiskLimitType.MAXIMUM_DRAWDOWN_FRACTION].value,
            latest[RiskLimitType.MAXIMUM_GROSS_EXPOSURE_FRACTION].value,
            latest[RiskLimitType.MAXIMUM_NET_EXPOSURE_FRACTION].value,
            self._whole_number(
                latest[RiskLimitType.MAXIMUM_ORDERS_PER_MINUTE].value, "orders per minute"
            ),
            self._whole_number(
                latest[RiskLimitType.MAXIMUM_CONSECUTIVE_LOSSES].value, "consecutive losses"
            ),
            latest[RiskLimitType.MAXIMUM_SECTOR_EXPOSURE_FRACTION].value,
            latest[RiskLimitType.MAXIMUM_STRATEGY_ALLOCATION_FRACTION].value,
            latest[RiskLimitType.MAXIMUM_SLIPPAGE_BPS].value,
            latest[RiskLimitType.MAXIMUM_OPTIONS_EXPOSURE].value,
            latest[RiskLimitType.MAXIMUM_PORTFOLIO_DELTA].value,
            latest[RiskLimitType.MAXIMUM_PORTFOLIO_GAMMA].value,
        )
        safety = await self.session.get(SafetyStateRecord, self.KILL_SWITCH_KEY)
        return PersistedRiskConfiguration(
            limits,
            safety.enabled if safety is not None else False,
            safety.reason if safety is not None else "not configured",
        )

    async def set_kill_switch(
        self,
        *,
        enabled: bool,
        reason: str,
        correlation_id: str,
        actor_id: str,
        occurred_at: datetime,
    ) -> None:
        if not reason.strip() or not correlation_id.strip() or not actor_id.strip():
            raise ValueError("kill-switch reason, correlation ID, and actor are required")
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError("kill-switch timestamp must be timezone-aware")
        state = await self.session.get(SafetyStateRecord, self.KILL_SWITCH_KEY)
        if state is None:
            self.session.add(
                SafetyStateRecord(
                    key=self.KILL_SWITCH_KEY,
                    enabled=enabled,
                    reason=reason,
                    updated_at=occurred_at.astimezone(UTC),
                    correlation_id=correlation_id,
                )
            )
        else:
            state.enabled = enabled
            state.reason = reason
            state.updated_at = occurred_at.astimezone(UTC)
            state.correlation_id = correlation_id
        self.session.add(
            AuditEventRecord(
                occurred_at=occurred_at.astimezone(UTC),
                actor_id=actor_id,
                action="risk.kill_switch.changed",
                resource_type="safety_state",
                resource_id=self.KILL_SWITCH_KEY,
                outcome="enabled" if enabled else "disabled",
                details={"reason": reason},
                correlation_id=correlation_id,
            )
        )
        await self.session.flush()

    async def activate_automatic_kill_if_required(
        self,
        context: PortfolioRiskContext,
        limits: RiskLimits,
        *,
        correlation_id: str,
    ) -> bool:
        reasons: list[str] = []
        if context.daily_pnl <= -(context.equity * limits.maximum_daily_loss_fraction):
            reasons.append("MAXIMUM_DAILY_LOSS")
        if context.weekly_pnl <= -(context.equity * limits.maximum_weekly_loss_fraction):
            reasons.append("MAXIMUM_WEEKLY_LOSS")
        if context.drawdown_fraction >= limits.maximum_drawdown_fraction:
            reasons.append("MAXIMUM_DRAWDOWN")
        if context.consecutive_losses >= limits.maximum_consecutive_losses:
            reasons.append("CONSECUTIVE_LOSS_CIRCUIT_BREAKER")
        if not reasons:
            return False
        await self.set_kill_switch(
            enabled=True,
            reason="automatic: " + ",".join(reasons),
            correlation_id=correlation_id,
            actor_id="risk-engine",
            occurred_at=context.evaluated_at,
        )
        return True

    @staticmethod
    def _whole_number(value: Decimal, label: str) -> int:
        converted = int(value)
        if value != converted or converted <= 0:
            raise ValueError(f"{label} risk limit must be a positive whole number")
        return converted
