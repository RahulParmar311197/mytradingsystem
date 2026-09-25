"""Deterministic, chronological logistic-regression baseline."""

from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite
from uuid import UUID, uuid4

import numpy as np
from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]
from sklearn.metrics import (  # type: ignore[import-untyped]
    accuracy_score,
    brier_score_loss,
    log_loss,
)
from sklearn.pipeline import Pipeline  # type: ignore[import-untyped]
from sklearn.preprocessing import StandardScaler  # type: ignore[import-untyped]


@dataclass(frozen=True, slots=True)
class FeatureDefinition:
    names: tuple[str, ...]
    version: str

    def __post_init__(self) -> None:
        if not self.version.strip() or not self.names or len(set(self.names)) != len(self.names):
            raise ValueError("feature names must be unique and feature version is required")
        if any(not name.strip() for name in self.names):
            raise ValueError("feature names cannot be empty")


@dataclass(frozen=True, slots=True)
class FeatureObservation:
    available_at: datetime
    values: tuple[tuple[str, float], ...]
    label: int | None = None

    def __post_init__(self) -> None:
        if self.available_at.tzinfo is None or self.available_at.utcoffset() is None:
            raise ValueError("feature availability timestamp must be timezone-aware")
        names = tuple(name for name, _ in self.values)
        if len(set(names)) != len(names) or any(not name.strip() for name in names):
            raise ValueError("feature observation names must be unique and non-empty")
        if any(not isfinite(value) for _, value in self.values):
            raise ValueError("feature values must be finite")
        if self.label not in (None, 0, 1):
            raise ValueError("classification label must be 0, 1, or absent")


@dataclass(frozen=True, slots=True)
class ModelEvaluation:
    observations: int
    accuracy: float
    brier_score: float
    log_loss: float
    expected_calibration_error: float


@dataclass(frozen=True, slots=True)
class FeatureImportance:
    name: str
    coefficient: float
    absolute_share: float


@dataclass(frozen=True, slots=True)
class FeatureDrift:
    name: str
    population_stability_index: float


@dataclass(frozen=True, slots=True)
class ModelPrediction:
    predicted_at: datetime
    probability: float
    model_version: str
    feature_version: str
    prediction_id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if self.predicted_at.tzinfo is None or self.predicted_at.utcoffset() is None:
            raise ValueError("prediction timestamp must be timezone-aware")
        if not isfinite(self.probability) or not 0 <= self.probability <= 1:
            raise ValueError("prediction probability must be finite and in [0, 1]")
        if not self.model_version.strip() or not self.feature_version.strip():
            raise ValueError("prediction model and feature versions are required")


@dataclass(frozen=True, slots=True)
class LogisticBaseline:
    model: Pipeline
    model_version: str
    feature_definition: FeatureDefinition
    trained_through: datetime
    validated_through: datetime
    validation: ModelEvaluation

    def feature_importance(self) -> tuple[FeatureImportance, ...]:
        classifier = self.model.named_steps["classifier"]
        coefficients = np.asarray(classifier.coef_[0], dtype=np.float64)
        total = float(np.abs(coefficients).sum())
        return tuple(
            FeatureImportance(
                name,
                float(coefficient),
                float(abs(coefficient) / total) if total else 0.0,
            )
            for name, coefficient in zip(self.feature_definition.names, coefficients, strict=True)
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


def _matrix(
    observations: tuple[FeatureObservation, ...],
    definition: FeatureDefinition,
    *,
    require_labels: bool,
) -> tuple[np.ndarray, np.ndarray | None]:
    rows: list[list[float]] = []
    labels: list[int] = []
    expected = set(definition.names)
    for observation in observations:
        values = dict(observation.values)
        if set(values) != expected:
            raise ValueError("observation does not match versioned feature definition")
        if require_labels and observation.label is None:
            raise ValueError("training and validation observations require labels")
        rows.append([values[name] for name in definition.names])
        if observation.label is not None:
            labels.append(observation.label)
    matrix = np.asarray(rows, dtype=np.float64)
    target = np.asarray(labels, dtype=np.int64) if labels else None
    return matrix, target


def expected_calibration_error(
    labels: np.ndarray, probabilities: np.ndarray, *, bins: int = 10
) -> float:
    if bins <= 0 or len(labels) != len(probabilities) or len(labels) == 0:
        raise ValueError("calibration requires aligned observations and positive bins")
    edges = np.linspace(0.0, 1.0, bins + 1)
    assignments = np.minimum(np.digitize(probabilities, edges[1:-1]), bins - 1)
    error = 0.0
    for index in range(bins):
        mask = assignments == index
        count = int(mask.sum())
        if count:
            error += (
                count
                / len(labels)
                * abs(float(probabilities[mask].mean()) - float(labels[mask].mean()))
            )
    return error


def population_stability_index(
    reference: tuple[FeatureObservation, ...],
    current: tuple[FeatureObservation, ...],
    definition: FeatureDefinition,
    *,
    as_of: datetime,
    bins: int = 10,
    epsilon: float = 0.0001,
) -> tuple[FeatureDrift, ...]:
    """Compare point-in-time feature populations using reference-quantile PSI bins."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("drift cutoff must be timezone-aware")
    if not reference or not current or bins < 2 or not 0 < epsilon < 1:
        raise ValueError("drift requires populations, at least two bins, and valid epsilon")
    if any(item.available_at > as_of for item in (*reference, *current)):
        raise ValueError("drift cannot use features unavailable at its cutoff")
    reference_matrix, _ = _matrix(reference, definition, require_labels=False)
    current_matrix, _ = _matrix(current, definition, require_labels=False)
    output: list[FeatureDrift] = []
    for index, name in enumerate(definition.names):
        quantiles = np.linspace(0.0, 1.0, bins + 1)
        internal = np.unique(np.quantile(reference_matrix[:, index], quantiles)[1:-1])
        reference_counts = np.histogram(
            reference_matrix[:, index], bins=[-np.inf, *internal, np.inf]
        )[0]
        current_counts = np.histogram(current_matrix[:, index], bins=[-np.inf, *internal, np.inf])[
            0
        ]
        reference_share = np.maximum(reference_counts / len(reference), epsilon)
        current_share = np.maximum(current_counts / len(current), epsilon)
        psi = float(
            np.sum((current_share - reference_share) * np.log(current_share / reference_share))
        )
        output.append(FeatureDrift(name, psi))
    return tuple(output)


def train_logistic_baseline(
    observations: tuple[FeatureObservation, ...],
    definition: FeatureDefinition,
    *,
    train_through: datetime,
    validate_through: datetime,
    model_version: str,
) -> LogisticBaseline:
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
    model = Pipeline(
        [
            ("scale", StandardScaler()),
            ("classifier", LogisticRegression(random_state=0, solver="lbfgs", max_iter=1000)),
        ]
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
    return LogisticBaseline(
        model, model_version, definition, train_through, validate_through, evaluation
    )
