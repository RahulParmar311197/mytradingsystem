from datetime import UTC, datetime, timedelta

import pytest

from packages.machine_learning import (
    FeatureDefinition,
    FeatureObservation,
    RandomForestBaseline,
    RandomForestConfig,
    train_random_forest_baseline,
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


def test_random_forest_challenger_is_deterministic_and_versioned() -> None:
    config = RandomForestConfig(estimators=50, maximum_depth=4, minimum_samples_leaf=2)

    def train() -> RandomForestBaseline:
        return train_random_forest_baseline(
            observations(),
            DEFINITION,
            train_through=NOW + timedelta(minutes=29),
            validate_through=NOW + timedelta(minutes=39),
            model_version="forest-v1",
            config=config,
        )

    first = train()
    second = train()
    assert first.validation == second.validation
    assert first.validation.observations == 10
    importance = first.feature_importance()
    assert tuple(item.name for item in importance) == DEFINITION.names
    assert sum(item.absolute_share for item in importance) == pytest.approx(1.0)
    sample = FeatureObservation(
        NOW + timedelta(minutes=40), (("momentum", 1.0), ("volatility", 0.2))
    )
    prediction = first.predict(sample, predicted_at=sample.available_at)
    assert 0 <= prediction.probability <= 1
    assert prediction.model_version == "forest-v1"


def test_random_forest_rejects_future_and_invalid_configuration() -> None:
    with pytest.raises(ValueError, match="positive"):
        RandomForestConfig(estimators=0)
    baseline = train_random_forest_baseline(
        observations(),
        DEFINITION,
        train_through=NOW + timedelta(minutes=29),
        validate_through=NOW + timedelta(minutes=39),
        model_version="forest-v1",
        config=RandomForestConfig(50, 4, 2),
    )
    with pytest.raises(ValueError, match="unavailable"):
        baseline.predict(
            FeatureObservation(
                NOW + timedelta(minutes=41), (("momentum", 1.0), ("volatility", 0.2))
            ),
            predicted_at=NOW + timedelta(minutes=40),
        )
