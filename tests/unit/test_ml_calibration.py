from datetime import UTC, datetime, timedelta

import pytest

from packages.machine_learning import (
    FeatureDefinition,
    FeatureObservation,
    train_platt_calibrated_baseline,
)

NOW = datetime(2026, 9, 19, 5, tzinfo=UTC)
DEFINITION = FeatureDefinition(("score",), "features-v1")


def observations(count: int = 36) -> tuple[FeatureObservation, ...]:
    return tuple(
        FeatureObservation(
            NOW + timedelta(minutes=index),
            (("score", (-1.0 if index % 2 == 0 else 1.0) * (1 + index / 100)),),
            index % 2,
        )
        for index in range(count)
    )


def test_platt_calibration_uses_three_disjoint_chronological_windows() -> None:
    baseline = train_platt_calibrated_baseline(
        observations(),
        DEFINITION,
        train_through=NOW + timedelta(minutes=19),
        calibrate_through=NOW + timedelta(minutes=27),
        validate_through=NOW + timedelta(minutes=35),
        model_version="logistic-platt-v1",
    )
    assert baseline.validation.observations == 8
    assert baseline.validation.accuracy == 1.0
    assert 0 <= baseline.validation.expected_calibration_error <= 1
    prediction = baseline.predict(
        FeatureObservation(NOW + timedelta(minutes=36), (("score", 2.0),)),
        predicted_at=NOW + timedelta(minutes=36),
    )
    assert 0.5 < prediction.probability <= 1
    assert prediction.model_version == "logistic-platt-v1"


def test_platt_calibration_rejects_future_prediction_features() -> None:
    baseline = train_platt_calibrated_baseline(
        observations(),
        DEFINITION,
        train_through=NOW + timedelta(minutes=19),
        calibrate_through=NOW + timedelta(minutes=27),
        validate_through=NOW + timedelta(minutes=35),
        model_version="logistic-platt-v1",
    )
    with pytest.raises(ValueError, match="unavailable"):
        baseline.predict(
            FeatureObservation(NOW + timedelta(minutes=37), (("score", 2.0),)),
            predicted_at=NOW + timedelta(minutes=36),
        )


def test_platt_calibration_requires_ordered_three_window_two_class_data() -> None:
    with pytest.raises(ValueError, match="both classes"):
        train_platt_calibrated_baseline(
            tuple(
                FeatureObservation(NOW + timedelta(minutes=index), (("score", float(index)),), 1)
                for index in range(9)
            ),
            DEFINITION,
            train_through=NOW + timedelta(minutes=2),
            calibrate_through=NOW + timedelta(minutes=5),
            validate_through=NOW + timedelta(minutes=8),
            model_version="logistic-platt-v1",
        )
