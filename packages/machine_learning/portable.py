"""Safe, JSON-only reconstruction for the fitted logistic baseline."""

import json
from dataclasses import dataclass
from datetime import datetime
from math import exp, isfinite
from typing import Any

import numpy as np

from packages.machine_learning.baseline import (
    FeatureDefinition,
    FeatureObservation,
    LogisticBaseline,
    ModelPrediction,
    _matrix,
)

FORMAT_VERSION = "portable-logistic-v1"
MAXIMUM_DOCUMENT_BYTES = 1_000_000


@dataclass(frozen=True, slots=True)
class PortableLogisticModel:
    """Minimal inference state reconstructed from validated JSON, never pickle."""

    model_version: str
    feature_definition: FeatureDefinition
    means: tuple[float, ...]
    scales: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float

    def __post_init__(self) -> None:
        width = len(self.feature_definition.names)
        if not self.model_version.strip():
            raise ValueError("model version is required")
        if any(len(values) != width for values in (self.means, self.scales, self.coefficients)):
            raise ValueError("portable model vectors must match the feature definition")
        values = (*self.means, *self.scales, *self.coefficients, self.intercept)
        if not all(isfinite(value) for value in values):
            raise ValueError("portable model parameters must be finite")
        if any(scale <= 0 for scale in self.scales):
            raise ValueError("portable model scales must be positive")

    @classmethod
    def from_baseline(cls, baseline: LogisticBaseline) -> "PortableLogisticModel":
        scaler = baseline.model.named_steps["scale"]
        classifier = baseline.model.named_steps["classifier"]
        return cls(
            baseline.model_version,
            baseline.feature_definition,
            tuple(float(value) for value in scaler.mean_),
            tuple(float(value) for value in scaler.scale_),
            tuple(float(value) for value in classifier.coef_[0]),
            float(classifier.intercept_[0]),
        )

    def to_bytes(self) -> bytes:
        payload = {
            "coefficients": self.coefficients,
            "feature_names": self.feature_definition.names,
            "feature_version": self.feature_definition.version,
            "format": FORMAT_VERSION,
            "intercept": self.intercept,
            "means": self.means,
            "model_version": self.model_version,
            "scales": self.scales,
        }
        return json.dumps(payload, allow_nan=False, separators=(",", ":"), sort_keys=True).encode()

    @classmethod
    def from_bytes(cls, payload: bytes) -> "PortableLogisticModel":
        if not payload or len(payload) > MAXIMUM_DOCUMENT_BYTES:
            raise ValueError("portable model document size is invalid")
        try:
            document = json.loads(payload, object_pairs_hook=_unique_object)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("portable model must be valid UTF-8 JSON") from error
        if not isinstance(document, dict) or set(document) != {
            "coefficients",
            "feature_names",
            "feature_version",
            "format",
            "intercept",
            "means",
            "model_version",
            "scales",
        }:
            raise ValueError("portable model has an unsupported schema")
        if document["format"] != FORMAT_VERSION:
            raise ValueError("portable model format is unsupported")
        try:
            names = _strings(document["feature_names"])
            definition = FeatureDefinition(names, _string(document["feature_version"]))
            return cls(
                _string(document["model_version"]),
                definition,
                _numbers(document["means"]),
                _numbers(document["scales"]),
                _numbers(document["coefficients"]),
                _number(document["intercept"]),
            )
        except (TypeError, ValueError) as error:
            raise ValueError("portable model contains invalid parameters") from error

    def predict(
        self, observation: FeatureObservation, *, predicted_at: datetime
    ) -> ModelPrediction:
        if predicted_at.tzinfo is None or predicted_at.utcoffset() is None:
            raise ValueError("prediction timestamp must be timezone-aware")
        if observation.available_at > predicted_at:
            raise ValueError("prediction cannot use features unavailable at prediction time")
        row = _matrix((observation,), self.feature_definition, require_labels=False)[0][0]
        standardized = (row - np.asarray(self.means)) / np.asarray(self.scales)
        score = float(np.dot(standardized, np.asarray(self.coefficients)) + self.intercept)
        probability = _sigmoid(score)
        return ModelPrediction(
            predicted_at, probability, self.model_version, self.feature_definition.version
        )


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1 / (1 + exp(-value))
    exponential = exp(value)
    return exponential / (1 + exponential)


def _string(value: Any) -> str:
    if not isinstance(value, str):
        raise TypeError
    return value


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError
    return tuple(value)


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError
    return float(value)


def _numbers(value: Any) -> tuple[float, ...]:
    if not isinstance(value, list):
        raise TypeError
    return tuple(_number(item) for item in value)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError("portable model contains duplicate fields")
        document[key] = value
    return document
