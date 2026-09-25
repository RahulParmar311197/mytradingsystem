from datetime import UTC, datetime, timedelta

import pytest

from packages.machine_learning import (
    FeatureDefinition,
    FeatureObservation,
    population_stability_index,
    train_logistic_baseline,
)

NOW = datetime(2026, 9, 19, 5, tzinfo=UTC)
DEFINITION = FeatureDefinition(("momentum", "volume"), "features-v1")


def observation(index: int, label: int) -> FeatureObservation:
    direction = -1.0 if label == 0 else 1.0
    return FeatureObservation(
        NOW + timedelta(minutes=index),
        (("momentum", direction * (1 + index / 100)), ("volume", direction)),
        label,
    )


def test_logistic_baseline_uses_chronological_split_and_predicts_point_in_time() -> None:
    observations = tuple(observation(index, index % 2) for index in range(20))
    baseline = train_logistic_baseline(
        observations,
        DEFINITION,
        train_through=NOW + timedelta(minutes=13),
        validate_through=NOW + timedelta(minutes=19),
        model_version="logistic-v1",
    )
    assert baseline.validation.observations == 6
    assert baseline.validation.accuracy == 1.0
    assert 0 <= baseline.validation.brier_score < 0.5
    assert 0 <= baseline.validation.expected_calibration_error <= 1
    importance = baseline.feature_importance()
    assert tuple(item.name for item in importance) == DEFINITION.names
    assert sum(item.absolute_share for item in importance) == pytest.approx(1.0)
    prediction = baseline.predict(
        FeatureObservation(NOW + timedelta(minutes=20), (("momentum", 2.0), ("volume", 1.0))),
        predicted_at=NOW + timedelta(minutes=20),
    )
    assert prediction.probability > 0.5
    assert prediction.model_version == "logistic-v1"
    assert prediction.feature_version == "features-v1"


def test_ml_baseline_fails_closed_on_leakage_and_schema_mismatch() -> None:
    observations = tuple(observation(index, index % 2) for index in range(8))
    baseline = train_logistic_baseline(
        observations,
        DEFINITION,
        train_through=NOW + timedelta(minutes=5),
        validate_through=NOW + timedelta(minutes=7),
        model_version="logistic-v1",
    )
    future = FeatureObservation(NOW + timedelta(minutes=9), (("momentum", 1.0), ("volume", 1.0)))
    with pytest.raises(ValueError, match="unavailable"):
        baseline.predict(future, predicted_at=NOW + timedelta(minutes=8))
    with pytest.raises(ValueError, match="feature definition"):
        baseline.predict(FeatureObservation(NOW, (("momentum", 1.0),)), predicted_at=NOW)


def test_ml_baseline_requires_ordered_labeled_two_class_training_data() -> None:
    ordered = tuple(observation(index, 1) for index in range(4))
    with pytest.raises(ValueError, match="both classes"):
        train_logistic_baseline(
            ordered,
            DEFINITION,
            train_through=NOW + timedelta(minutes=2),
            validate_through=NOW + timedelta(minutes=3),
            model_version="logistic-v1",
        )
    with pytest.raises(ValueError, match="chronological"):
        train_logistic_baseline(
            tuple(reversed(tuple(observation(index, index % 2) for index in range(4)))),
            DEFINITION,
            train_through=NOW + timedelta(minutes=2),
            validate_through=NOW + timedelta(minutes=3),
            model_version="logistic-v1",
        )


def test_population_stability_index_detects_shift_without_future_data() -> None:
    reference = tuple(
        FeatureObservation(
            NOW + timedelta(minutes=index),
            (("momentum", float(index)), ("volume", float(index % 3))),
        )
        for index in range(20)
    )
    current = tuple(
        FeatureObservation(
            NOW + timedelta(minutes=20 + index),
            (("momentum", float(index + 100)), ("volume", float(index % 3))),
        )
        for index in range(20)
    )
    drift = population_stability_index(
        reference, current, DEFINITION, as_of=NOW + timedelta(minutes=39), bins=5
    )
    by_name = {item.name: item.population_stability_index for item in drift}
    assert by_name["momentum"] > 1
    assert by_name["volume"] < 0.1
    with pytest.raises(ValueError, match="unavailable"):
        population_stability_index(
            reference,
            current,
            DEFINITION,
            as_of=NOW + timedelta(minutes=38),
            bins=5,
        )
