"""Chronological Platt calibration with a dedicated calibration window."""

from dataclasses import dataclass
from datetime import datetime

import numpy as np
from numpy.typing import NDArray
from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]
from sklearn.metrics import (  # type: ignore[import-untyped]
    accuracy_score,
    brier_score_loss,
    log_loss,
)
from sklearn.pipeline import Pipeline  # type: ignore[import-untyped]
from sklearn.preprocessing import StandardScaler  # type: ignore[import-untyped]

from packages.machine_learning.baseline import (
    FeatureDefinition,
    FeatureObservation,
    ModelEvaluation,
    ModelPrediction,
    _matrix,
    expected_calibration_error,
)


def _logits(probabilities: NDArray[np.float64]) -> NDArray[np.float64]:
    clipped = np.clip(probabilities, 1e-12, 1 - 1e-12)
    result: NDArray[np.float64] = np.log(clipped / (1 - clipped)).reshape(-1, 1)
    return result


@dataclass(frozen=True, slots=True)
class PlattCalibratedBaseline:
    base_model: Pipeline
    calibrator: LogisticRegression
    model_version: str
    feature_definition: FeatureDefinition
    trained_through: datetime
    calibrated_through: datetime
    validated_through: datetime
    validation: ModelEvaluation

    def predict(
        self, observation: FeatureObservation, *, predicted_at: datetime
    ) -> ModelPrediction:
        if predicted_at.tzinfo is None or predicted_at.utcoffset() is None:
            raise ValueError("prediction timestamp must be timezone-aware")
        if observation.available_at > predicted_at:
            raise ValueError("prediction cannot use features unavailable at prediction time")
        matrix = _matrix((observation,), self.feature_definition, require_labels=False)[0]
        raw = self.base_model.predict_proba(matrix)[:, 1]
        probability = float(self.calibrator.predict_proba(_logits(raw))[0, 1])
        return ModelPrediction(
            predicted_at, probability, self.model_version, self.feature_definition.version
        )


def train_platt_calibrated_baseline(
    observations: tuple[FeatureObservation, ...],
    definition: FeatureDefinition,
    *,
    train_through: datetime,
    calibrate_through: datetime,
    validate_through: datetime,
    model_version: str,
) -> PlattCalibratedBaseline:
    cutoffs = (train_through, calibrate_through, validate_through)
    if any(value.tzinfo is None or value.utcoffset() is None for value in cutoffs):
        raise ValueError("split timestamps must be timezone-aware")
    if not train_through < calibrate_through < validate_through:
        raise ValueError("training, calibration, and validation cutoffs must be chronological")
    if not model_version.strip():
        raise ValueError("model version is required")
    if tuple(sorted(observations, key=lambda item: item.available_at)) != observations:
        raise ValueError("observations must be chronological")
    train = tuple(item for item in observations if item.available_at <= train_through)
    calibration = tuple(
        item for item in observations if train_through < item.available_at <= calibrate_through
    )
    validation = tuple(
        item for item in observations if calibrate_through < item.available_at <= validate_through
    )
    if not train or not calibration or not validation:
        raise ValueError("non-empty training, calibration, and validation windows are required")
    x_train, y_train = _matrix(train, definition, require_labels=True)
    x_calibration, y_calibration = _matrix(calibration, definition, require_labels=True)
    x_validation, y_validation = _matrix(validation, definition, require_labels=True)
    targets = (y_train, y_calibration, y_validation)
    if any(target is None or len(set(target.tolist())) != 2 for target in targets):
        raise ValueError("every model window must contain both classes")
    if y_train is None or y_calibration is None or y_validation is None:
        raise RuntimeError("labeled matrix unexpectedly omitted targets")
    base = Pipeline(
        [
            ("scale", StandardScaler()),
            ("classifier", LogisticRegression(random_state=0, solver="lbfgs", max_iter=1000)),
        ]
    )
    base.fit(x_train, y_train)
    calibrator = LogisticRegression(random_state=0, solver="lbfgs", max_iter=1000)
    calibrator.fit(_logits(base.predict_proba(x_calibration)[:, 1]), y_calibration)
    probabilities = calibrator.predict_proba(_logits(base.predict_proba(x_validation)[:, 1]))[:, 1]
    predictions = (probabilities >= 0.5).astype(np.int64)
    evaluation = ModelEvaluation(
        len(validation),
        float(accuracy_score(y_validation, predictions)),
        float(brier_score_loss(y_validation, probabilities)),
        float(log_loss(y_validation, probabilities, labels=[0, 1])),
        expected_calibration_error(y_validation, probabilities),
    )
    return PlattCalibratedBaseline(
        base,
        calibrator,
        model_version,
        definition,
        train_through,
        calibrate_through,
        validate_through,
        evaluation,
    )
