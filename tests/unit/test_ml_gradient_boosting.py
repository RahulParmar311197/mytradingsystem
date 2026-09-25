from datetime import UTC, datetime, timedelta

import pytest

from packages.machine_learning import (
    FeatureDefinition,
    FeatureObservation,
    GradientBoostingBaseline,
    GradientBoostingConfig,
    train_gradient_boosting_baseline,
)

NOW = datetime(2026, 9, 20, 5, tzinfo=UTC)
DEFINITION = FeatureDefinition(("momentum", "volatility"), "features-v1")


def observations() -> tuple[FeatureObservation, ...]:
    return tuple(
        FeatureObservation(
            NOW + timedelta(minutes=index),
            (
                ("momentum", -1.0 if index % 2 == 0 else 1.0),
                ("volatility", float(index % 5) / 5),
            ),
            index % 2,
        )
        for index in range(40)
    )


def test_gradient_boosting_challenger_is_deterministic_and_versioned() -> None:
    config = GradientBoostingConfig(40, 0.05, 2, 2, 7)

    def train() -> GradientBoostingBaseline:
        return train_gradient_boosting_baseline(
            observations(),
            DEFINITION,
            train_through=NOW + timedelta(minutes=29),
            validate_through=NOW + timedelta(minutes=39),
            model_version="boost-v1",
            config=config,
        )

    first = train()
    second = train()
    assert first.validation == second.validation
    assert (
        first.model.predict_proba([[1.0, 0.2]]).tolist()
        == second.model.predict_proba([[1.0, 0.2]]).tolist()
    )
    importance = first.feature_importance()
    assert tuple(item.name for item in importance) == DEFINITION.names
    assert sum(item.absolute_share for item in importance) == pytest.approx(1.0)
    sample = FeatureObservation(
        NOW + timedelta(minutes=40), (("momentum", 1.0), ("volatility", 0.2))
    )
    prediction = first.predict(sample, predicted_at=sample.available_at)
    assert 0 <= prediction.probability <= 1
    assert prediction.model_version == "boost-v1"


def test_gradient_boosting_rejects_invalid_configuration_and_future_features() -> None:
    with pytest.raises(ValueError, match="positive"):
        GradientBoostingConfig(estimators=0)
    with pytest.raises(ValueError, match="learning rate"):
        GradientBoostingConfig(learning_rate=1.1)
    baseline = train_gradient_boosting_baseline(
        observations(),
        DEFINITION,
        train_through=NOW + timedelta(minutes=29),
        validate_through=NOW + timedelta(minutes=39),
        model_version="boost-v1",
        config=GradientBoostingConfig(40, 0.05, 2, 2),
    )
    with pytest.raises(ValueError, match="unavailable"):
        baseline.predict(
            FeatureObservation(
                NOW + timedelta(minutes=41), (("momentum", 1.0), ("volatility", 0.2))
            ),
            predicted_at=NOW + timedelta(minutes=40),
        )


def test_gradient_boosting_enforces_chronological_training_boundaries() -> None:
    reversed_observations = tuple(reversed(observations()))
    with pytest.raises(ValueError, match="chronological"):
        train_gradient_boosting_baseline(
            reversed_observations,
            DEFINITION,
            train_through=NOW + timedelta(minutes=29),
            validate_through=NOW + timedelta(minutes=39),
            model_version="boost-v1",
        )
