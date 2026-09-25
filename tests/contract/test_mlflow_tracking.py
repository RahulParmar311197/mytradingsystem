from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from types import TracebackType
from typing import Any

import pytest

from packages.machine_learning import (
    ArtifactReference,
    MLflowMetadataExporter,
)


@dataclass
class RunInfo:
    run_id: str


@dataclass
class Run:
    info: RunInfo


class RunContext(AbstractContextManager[Run]):
    def __init__(self, run_id: str) -> None:
        self.run = Run(RunInfo(run_id))
        self.exited = False

    def __enter__(self) -> Run:
        return self.run

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.exited = True


class FakeMLflow:
    def __init__(self) -> None:
        self.experiment: str | None = None
        self.run_name: str | None = None
        self.tags: dict[str, str] = {}
        self.params: dict[str, str] = {}
        self.metrics: dict[str, float] = {}
        self.context = RunContext("run-123")

    def set_experiment(self, experiment_name: str) -> None:
        self.experiment = experiment_name

    def start_run(self, *, run_name: str, tags: dict[str, str]) -> RunContext:
        self.run_name = run_name
        self.tags = tags
        return self.context

    def log_params(self, params: dict[str, str]) -> None:
        self.params = params

    def log_metrics(self, metrics: dict[str, float]) -> None:
        self.metrics = metrics


ARTIFACT = ArtifactReference("artifact+s3://models/models/abc.artifact", "a" * 64, 42)


def test_mlflow_exporter_logs_only_metadata_metrics_and_safety_tags() -> None:
    client = FakeMLflow()
    exporter = MLflowMetadataExporter(client, experiment_name="offline-research")
    record = exporter.export(
        model_name="direction",
        model_version="logistic-v1",
        feature_version="features-v2",
        trained_at=datetime(2026, 9, 20, tzinfo=UTC),
        metrics={"brier_score": 0.2, "log_loss": 0.4},
        artifact=ARTIFACT,
    )
    assert record.run_id == "run-123"
    assert client.experiment == "offline-research"
    assert client.run_name == "direction:logistic-v1"
    assert client.tags == {
        "authority": "scoring-only",
        "automatic_promotion": "forbidden",
        "evidence_format": "metadata-only-v1",
    }
    assert client.params["artifact_uri"] == ARTIFACT.uri
    assert client.params["artifact_sha256"] == ARTIFACT.sha256
    assert client.metrics == {"brier_score": 0.2, "log_loss": 0.4}
    assert client.context.exited


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("model_name", "", "identity"),
        ("metrics", {}, "metrics"),
        ("metrics", {"loss": float("nan")}, "metrics"),
        ("trained_at", datetime(2026, 9, 20), "timezone-aware"),
        ("artifact", ArtifactReference("uri", "bad", 1), "artifact"),
    ),
)
def test_mlflow_exporter_rejects_invalid_evidence(field: str, value: Any, message: str) -> None:
    arguments: dict[str, Any] = {
        "model_name": "direction",
        "model_version": "v1",
        "feature_version": "features-v1",
        "trained_at": datetime(2026, 9, 20, tzinfo=UTC),
        "metrics": {"loss": 0.2},
        "artifact": ARTIFACT,
    }
    arguments[field] = value
    with pytest.raises(ValueError, match=message):
        MLflowMetadataExporter(FakeMLflow(), experiment_name="research").export(**arguments)


def test_mlflow_exporter_requires_run_identity_and_experiment() -> None:
    with pytest.raises(ValueError, match="experiment"):
        MLflowMetadataExporter(FakeMLflow(), experiment_name=" ")
    client = FakeMLflow()
    client.context = RunContext(" ")
    with pytest.raises(ValueError, match="run ID"):
        MLflowMetadataExporter(client, experiment_name="research").export(
            model_name="direction",
            model_version="v1",
            feature_version="features-v1",
            trained_at=datetime(2026, 9, 20, tzinfo=UTC),
            metrics={"loss": 0.2},
            artifact=ARTIFACT,
        )
