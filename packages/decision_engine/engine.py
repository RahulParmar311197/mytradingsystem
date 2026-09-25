"""Deterministic decision aggregation; this module cannot execute orders."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from packages.domain.models import SignalAction
from packages.strategies.engine import StrategySignal


@dataclass(frozen=True, slots=True)
class DecisionConfig:
    technical_weight: Decimal = Decimal("0.20")
    smc_weight: Decimal = Decimal("0.20")
    regime_weight: Decimal = Decimal("0.15")
    volume_weight: Decimal = Decimal("0.10")
    options_weight: Decimal = Decimal("0.05")
    ml_weight: Decimal = Decimal("0.05")
    data_quality_weight: Decimal = Decimal("0.15")
    risk_context_weight: Decimal = Decimal("0.10")
    minimum_confidence: Decimal = Decimal("0.65")
    minimum_data_quality: Decimal = Decimal("0.80")
    minimum_risk_reward: Decimal = Decimal("1.5")
    version: str = "decision-rules-v1"

    def __post_init__(self) -> None:
        weights = self.weights
        if any(weight < 0 for weight in weights.values()):
            raise ValueError("decision weights cannot be negative")
        if sum(weights.values(), Decimal(0)) != Decimal(1):
            raise ValueError("decision weights must sum exactly to 1")
        if not Decimal(0) <= self.minimum_confidence <= Decimal(1):
            raise ValueError("minimum confidence must be between 0 and 1")
        if not Decimal(0) <= self.minimum_data_quality <= Decimal(1):
            raise ValueError("minimum data quality must be between 0 and 1")
        if self.minimum_risk_reward <= 0:
            raise ValueError("minimum risk/reward must be positive")
        if not self.version.strip():
            raise ValueError("decision version cannot be empty")

    @property
    def weights(self) -> dict[str, Decimal]:
        return {
            "technical": self.technical_weight,
            "smc_ict": self.smc_weight,
            "regime": self.regime_weight,
            "volume": self.volume_weight,
            "options": self.options_weight,
            "ml": self.ml_weight,
            "data_quality": self.data_quality_weight,
            "risk_context": self.risk_context_weight,
        }


@dataclass(frozen=True, slots=True)
class DecisionInputs:
    strategy_signal: StrategySignal
    technical_score: Decimal
    smc_ict_score: Decimal
    regime_compatibility: Decimal
    volume_score: Decimal
    options_score: Decimal
    data_quality_score: Decimal
    risk_context_score: Decimal
    ml_probability: Decimal | None = None

    def __post_init__(self) -> None:
        scores = (
            self.technical_score,
            self.smc_ict_score,
            self.regime_compatibility,
            self.volume_score,
            self.options_score,
            self.data_quality_score,
            self.risk_context_score,
        )
        if any(not Decimal(0) <= score <= Decimal(1) for score in scores):
            raise ValueError("decision scores must be between 0 and 1")
        if self.ml_probability is not None and not Decimal(0) <= self.ml_probability <= Decimal(1):
            raise ValueError("ML probability must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class DecisionResult:
    id: UUID
    timestamp: datetime
    instrument_id: UUID
    strategy: str
    strategy_version: str
    decision_version: str
    action: SignalAction
    confidence: Decimal
    contributing_factors: dict[str, Decimal | str]
    rejection_reasons: tuple[str, ...]
    proposed_entry: Decimal | None
    proposed_stop: Decimal | None
    proposed_targets: tuple[Decimal, ...]
    expected_risk_reward: Decimal | None
    requested_risk_fraction: Decimal
    data_snapshot_id: str
    requires_risk_approval: bool
    explanation: str


def _risk_reward(signal: StrategySignal) -> Decimal | None:
    if (
        signal.proposed_entry is None
        or signal.proposed_stop is None
        or not signal.proposed_targets
        or signal.action not in (SignalAction.LONG, SignalAction.SHORT)
    ):
        return None
    entry, stop, target = signal.proposed_entry, signal.proposed_stop, signal.proposed_targets[0]
    if signal.action is SignalAction.LONG:
        risk, reward = entry - stop, target - entry
    else:
        risk, reward = stop - entry, entry - target
    if risk <= 0 or reward <= 0:
        return None
    return reward / risk


def _weighted_confidence(
    inputs: DecisionInputs, config: DecisionConfig
) -> tuple[Decimal, dict[str, Decimal]]:
    scores = {
        "technical": inputs.technical_score,
        "smc_ict": inputs.smc_ict_score,
        "regime": inputs.regime_compatibility,
        "volume": inputs.volume_score,
        "options": inputs.options_score,
        "data_quality": inputs.data_quality_score,
        "risk_context": inputs.risk_context_score,
    }
    if inputs.ml_probability is not None:
        scores["ml"] = inputs.ml_probability
    active_weight = sum((config.weights[name] for name in scores), Decimal(0))
    if active_weight == 0:
        return Decimal(0), scores
    confidence = (
        sum((score * config.weights[name] for name, score in scores.items()), Decimal(0))
        / active_weight
    )
    return confidence, scores


def decide(inputs: DecisionInputs, config: DecisionConfig | None = None) -> DecisionResult:
    """Convert one strategy proposal and validated scores into a non-executable decision."""
    rules = config or DecisionConfig()
    signal = inputs.strategy_signal
    confidence, scores = _weighted_confidence(inputs, rules)
    rejection_reasons = list(signal.rejection_reasons)
    risk_reward = _risk_reward(signal)

    action = signal.action
    if action is SignalAction.NO_TRADE:
        rejection_reasons.append("STRATEGY_NO_TRADE")
    elif action in (SignalAction.LONG, SignalAction.SHORT):
        if inputs.data_quality_score < rules.minimum_data_quality:
            rejection_reasons.append("DATA_QUALITY_BELOW_THRESHOLD")
        if confidence < rules.minimum_confidence:
            rejection_reasons.append("CONFIDENCE_BELOW_THRESHOLD")
        if risk_reward is None:
            rejection_reasons.append("INVALID_PRICE_GEOMETRY")
        elif risk_reward < rules.minimum_risk_reward:
            rejection_reasons.append("RISK_REWARD_BELOW_THRESHOLD")
        if rejection_reasons:
            action = SignalAction.NO_TRADE

    entry_action = action in (SignalAction.LONG, SignalAction.SHORT)
    factors: dict[str, Decimal | str] = {**scores, "strategy_action": signal.action.value}
    factors["strategy_confidence"] = signal.confidence
    return DecisionResult(
        uuid4(),
        signal.timestamp.astimezone(UTC),
        signal.instrument_id,
        signal.strategy,
        signal.strategy_version,
        rules.version,
        action,
        confidence,
        factors,
        tuple(dict.fromkeys(rejection_reasons)),
        signal.proposed_entry if entry_action else None,
        signal.proposed_stop if entry_action else None,
        signal.proposed_targets if entry_action else (),
        risk_reward if entry_action else None,
        signal.requested_risk_fraction if entry_action else Decimal(0),
        signal.data_snapshot_id,
        entry_action,
        (
            "Decision passed deterministic gates and requires independent risk approval"
            if entry_action
            else (
                f"Decision is {action.value}: "
                f"{', '.join(dict.fromkeys(rejection_reasons)) or signal.explanation}"
            )
        ),
    )
