"""Metadata-only MLflow experiment export with no model deserialization or promotion."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Any, Protocol

from packages.machine_learning.artifacts import ArtifactReference


class MLflowModule(Protocol):
    """Small subset of the MLflow fluent API used by the exporter."""

    def set_experiment(self, experiment_name: str) -> Any: ...

    def start_run(self, *, run_name: str, tags: Mapping[str, str]) -> Any: ...

    def log_params(self, params: Mapping[str, str]) -> None: ...

    def log_metrics(self, metrics: Mapping[str, float]) -> None: ...


@dataclass(frozen=True, slots=True)
class MLflowRunRecord:
    run_id: str
    experiment_name: str
    model_name: str
    model_version: str
    feature_version: str
    artifact: ArtifactReference


class MLflowMetadataExporter:
    """Export immutable model evidence; never logs binaries or changes registry stage."""

    def __init__(self, client: MLflowModule, *, experiment_name: str) -> None:
        if not experiment_name.strip():
            raise ValueError("MLflow experiment name is required")
        self.client = client
        self.experiment_name = experiment_name

    def export(
        self,
        *,
        model_name: str,
        model_version: str,
        feature_version: str,
        trained_at: datetime,
        metrics: Mapping[str, float],
        artifact: ArtifactReference,
    ) -> MLflowRunRecord:
        if any(not value.strip() for value in (model_name, model_version, feature_version)):
            raise ValueError("model and feature identity are required")
        if trained_at.tzinfo is None or trained_at.utcoffset() is None:
            raise ValueError("training timestamp must be timezone-aware")
        if not metrics or any(
            not name.strip() or not isfinite(value) for name, value in metrics.items()
        ):
            raise ValueError("MLflow metrics must be named, finite, and non-empty")
        if (
            len(artifact.sha256) != 64
            or any(character not in "0123456789abcdef" for character in artifact.sha256)
            or artifact.size_bytes <= 0
            or not artifact.uri.strip()
        ):
            raise ValueError("artifact evidence is invalid")
        params = {
            "artifact_sha256": artifact.sha256,
            "artifact_size_bytes": str(artifact.size_bytes),
            "artifact_uri": artifact.uri,
            "feature_version": feature_version,
            "model_name": model_name,
            "model_version": model_version,
            "trained_at": trained_at.isoformat(),
        }
        tags = {
            "authority": "scoring-only",
            "automatic_promotion": "forbidden",
            "evidence_format": "metadata-only-v1",
        }
        self.client.set_experiment(self.experiment_name)
        with self.client.start_run(run_name=f"{model_name}:{model_version}", tags=tags) as run:
            self.client.log_params(params)
            self.client.log_metrics(dict(metrics))
            run_id = _run_id(run)
        return MLflowRunRecord(
            run_id,
            self.experiment_name,
            model_name,
            model_version,
            feature_version,
            artifact,
        )


def _run_id(run: Any) -> str:
    info = getattr(run, "info", None)
    run_id = getattr(info, "run_id", None)
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("MLflow run did not provide a run ID")
    return run_id
