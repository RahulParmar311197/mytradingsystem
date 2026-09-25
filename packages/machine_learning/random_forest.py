"""Deterministic chronological random-forest challenger baseline."""

from dataclasses import dataclass
from datetime import datetime

import numpy as np
from sklearn.ensemble import RandomForestClassifier  # type: ignore[import-untyped]
from sklearn.metrics import (  # type: ignore[import-untyped]
    accuracy_score,
    brier_score_loss,
    log_loss,
)

from packages.machine_learning.baseline import (
    FeatureDefinition,
    FeatureImportance,
    FeatureObservation,
    ModelEvaluation,
    ModelPrediction,
    _matrix,
    expected_calibration_error,
)


@dataclass(frozen=True, slots=True)
class RandomForestConfig:
    estimators: int = 200
    maximum_depth: int = 6
    minimum_samples_leaf: int = 10
    random_seed: int = 0

    def __post_init__(self) -> None:
        if min(self.estimators, self.maximum_depth, self.minimum_samples_leaf) <= 0:
            raise ValueError("random-forest size controls must be positive")


@dataclass(frozen=True, slots=True)
class RandomForestBaseline:
    model: RandomForestClassifier
    model_version: str
    feature_definition: FeatureDefinition
    trained_through: datetime
    validated_through: datetime
    validation: ModelEvaluation

    def feature_importance(self) -> tuple[FeatureImportance, ...]:
        values = np.asarray(self.model.feature_importances_, dtype=np.float64)
        total = float(values.sum())
        return tuple(
            FeatureImportance(name, float(value), float(value / total) if total else 0.0)
            for name, value in zip(self.feature_definition.names, values, strict=True)
        )

    def predict(
        self, observation: FeatureObservation, *, predicted_at: datetime
    ) -> ModelPrediction:
        if predicted_at.tzinfo is None or predicted_at.utcoffset() is None:
            raise ValueError("prediction timestamp must be timezone-aware")
        if observation.available_at > predicted_at:
            raise ValueError("prediction cannot use features unavailable at prediction time")
        matrix = _matrix((observation,), self.feature_definition, require_labels=False)[0]
        probability = float(self.model.predict_proba(matrix)[0, 1])
        return ModelPrediction(
            predicted_at, probability, self.model_version, self.feature_definition.version
        )


def train_random_forest_baseline(
    observations: tuple[FeatureObservation, ...],
    definition: FeatureDefinition,
    *,
    train_through: datetime,
    validate_through: datetime,
    model_version: str,
    config: RandomForestConfig | None = None,
) -> RandomForestBaseline:
    config = config or RandomForestConfig()
    if not model_version.strip():
        raise ValueError("model version is required")
    if any(
        value.tzinfo is None or value.utcoffset() is None
        for value in (train_through, validate_through)
    ):
        raise ValueError("split timestamps must be timezone-aware")
    if train_through >= validate_through:
        raise ValueError("validation cutoff must follow training cutoff")
    if tuple(sorted(observations, key=lambda item: item.available_at)) != observations:
        raise ValueError("observations must be chronological")
    train = tuple(item for item in observations if item.available_at <= train_through)
    validation = tuple(
        item for item in observations if train_through < item.available_at <= validate_through
    )
    if not train or not validation:
        raise ValueError("chronological training and validation sets are required")
    x_train, y_train = _matrix(train, definition, require_labels=True)
    x_validation, y_validation = _matrix(validation, definition, require_labels=True)
    if y_train is None or y_validation is None or len(set(y_train.tolist())) != 2:
        raise ValueError("training labels must contain both classes")
    model = RandomForestClassifier(
        n_estimators=config.estimators,
        max_depth=config.maximum_depth,
        min_samples_leaf=config.minimum_samples_leaf,
        random_state=config.random_seed,
        n_jobs=1,
    )
    model.fit(x_train, y_train)
    probabilities = model.predict_proba(x_validation)[:, 1]
    predictions = (probabilities >= 0.5).astype(np.int64)
    evaluation = ModelEvaluation(
        len(validation),
        float(accuracy_score(y_validation, predictions)),
        float(brier_score_loss(y_validation, probabilities)),
        float(log_loss(y_validation, probabilities, labels=[0, 1])),
        expected_calibration_error(y_validation, probabilities),
    )
    return RandomForestBaseline(
        model, model_version, definition, train_through, validate_through, evaluation
    )
