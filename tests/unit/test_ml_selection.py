from datetime import UTC, datetime
from uuid import uuid4

import pytest

from packages.machine_learning import (
    MetricDirection,
    MetricGuardrail,
    ModelComparisonPolicy,
    ModelStage,
    RegisteredModel,
    compare_models,
)

NOW = datetime(2026, 9, 19, 5, tzinfo=UTC)


def model(
    version: str, metrics: dict[str, float], feature_version: str = "features-v1"
) -> RegisteredModel:
    return RegisteredModel(
        uuid4(),
        "direction",
        version,
        feature_version,
        NOW,
        f"s3://models/direction/{version}",
        "a" * 64,
        ModelStage.CHALLENGER,
        metrics,
    )


POLICY = ModelComparisonPolicy(
    "brier",
    MetricDirection.LOWER_IS_BETTER,
    0.01,
    (MetricGuardrail("accuracy", MetricDirection.HIGHER_IS_BETTER, 0.02),),
)


def test_challenger_requires_primary_improvement_and_guardrails() -> None:
    champion = model("1", {"brier": 0.20, "accuracy": 0.70})
    accepted = compare_models(champion, model("2", {"brier": 0.18, "accuracy": 0.69}), POLICY)
    assert accepted.challenger_accepted is True
    assert accepted.primary_improvement == pytest.approx(0.02)
    assert accepted.reason_codes == ("CHALLENGER_ACCEPTED",)

    rejected = compare_models(champion, model("3", {"brier": 0.18, "accuracy": 0.67}), POLICY)
    assert rejected.challenger_accepted is False
    assert rejected.reason_codes == ("GUARDRAIL_REGRESSION:accuracy",)


def test_challenger_comparison_fails_closed_on_incompatible_evidence() -> None:
    champion = model("1", {"brier": 0.20, "accuracy": 0.70})
    with pytest.raises(ValueError, match="feature versions"):
        compare_models(
            champion,
            model("2", {"brier": 0.18, "accuracy": 0.72}, "features-v2"),
            POLICY,
        )
    with pytest.raises(ValueError, match="missing"):
        compare_models(champion, model("2", {"brier": 0.18}), POLICY)


def test_challenger_below_primary_threshold_is_not_accepted() -> None:
    comparison = compare_models(
        model("1", {"brier": 0.20, "accuracy": 0.70}),
        model("2", {"brier": 0.195, "accuracy": 0.71}),
        POLICY,
    )
    assert comparison.challenger_accepted is False
    assert comparison.reason_codes == ("PRIMARY_IMPROVEMENT_BELOW_THRESHOLD",)
