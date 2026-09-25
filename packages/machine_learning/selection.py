"""Transparent champion/challenger comparison without automatic promotion."""

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from packages.machine_learning.persistence import RegisteredModel


class MetricDirection(StrEnum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


@dataclass(frozen=True, slots=True)
class MetricGuardrail:
    metric: str
    direction: MetricDirection
    maximum_regression: float

    def __post_init__(self) -> None:
        if (
            not self.metric.strip()
            or not isfinite(self.maximum_regression)
            or self.maximum_regression < 0
        ):
            raise ValueError(
                "guardrail metric is required and regression must be finite and non-negative"
            )


@dataclass(frozen=True, slots=True)
class ModelComparisonPolicy:
    primary_metric: str
    primary_direction: MetricDirection
    minimum_improvement: float
    guardrails: tuple[MetricGuardrail, ...] = ()

    def __post_init__(self) -> None:
        if not self.primary_metric.strip() or not isfinite(self.minimum_improvement):
            raise ValueError("primary metric and finite improvement are required")
        if self.minimum_improvement < 0:
            raise ValueError("minimum improvement cannot be negative")
        names = tuple(item.metric for item in self.guardrails)
        if len(set(names)) != len(names) or self.primary_metric in names:
            raise ValueError(
                "guardrail metrics must be unique and distinct from the primary metric"
            )


@dataclass(frozen=True, slots=True)
class ModelComparison:
    challenger_accepted: bool
    primary_improvement: float
    reason_codes: tuple[str, ...]


def _improvement(champion: float, challenger: float, direction: MetricDirection) -> float:
    return (
        challenger - champion
        if direction is MetricDirection.HIGHER_IS_BETTER
        else champion - challenger
    )


def compare_models(
    champion: RegisteredModel,
    challenger: RegisteredModel,
    policy: ModelComparisonPolicy,
) -> ModelComparison:
    """Evaluate explicit metrics only; callers still require an audited promotion action."""
    if champion.name != challenger.name:
        raise ValueError("champion and challenger must belong to the same model family")
    if champion.feature_version != challenger.feature_version:
        raise ValueError("champion and challenger feature versions must match")
    required = {policy.primary_metric, *(item.metric for item in policy.guardrails)}
    missing = sorted((required - champion.metrics.keys()) | (required - challenger.metrics.keys()))
    if missing:
        raise ValueError(f"comparison metrics are missing: {', '.join(missing)}")
    if any(
        not isfinite(model.metrics[metric])
        for model in (champion, challenger)
        for metric in required
    ):
        raise ValueError("comparison metrics must be finite")
    primary = _improvement(
        champion.metrics[policy.primary_metric],
        challenger.metrics[policy.primary_metric],
        policy.primary_direction,
    )
    reasons: list[str] = []
    if primary < policy.minimum_improvement:
        reasons.append("PRIMARY_IMPROVEMENT_BELOW_THRESHOLD")
    for guardrail in policy.guardrails:
        improvement = _improvement(
            champion.metrics[guardrail.metric],
            challenger.metrics[guardrail.metric],
            guardrail.direction,
        )
        if improvement < -guardrail.maximum_regression:
            reasons.append(f"GUARDRAIL_REGRESSION:{guardrail.metric}")
    return ModelComparison(not reasons, primary, tuple(reasons) or ("CHALLENGER_ACCEPTED",))
