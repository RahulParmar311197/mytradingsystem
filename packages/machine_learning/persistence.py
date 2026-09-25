"""Metadata-only model registry and idempotent prediction log."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from math import isfinite
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models import MLModelVersionRecord, MLPredictionRecord
from packages.machine_learning.baseline import FeatureObservation, ModelPrediction


class ModelStage(StrEnum):
    CHALLENGER = "challenger"
    CHAMPION = "champion"
    ARCHIVED = "archived"


@dataclass(frozen=True, slots=True)
class RegisteredModel:
    id: UUID
    name: str
    version: str
    feature_version: str
    trained_at: datetime
    artifact_uri: str
    artifact_sha256: str
    stage: ModelStage
    metrics: dict[str, float]


class ModelRegistry:
    """Register verified artifact metadata; model binaries are never deserialized here."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def register(
        self,
        *,
        name: str,
        version: str,
        feature_version: str,
        trained_at: datetime,
        artifact_uri: str,
        artifact_sha256: str,
        metrics: dict[str, float],
    ) -> RegisteredModel:
        if trained_at.tzinfo is None or trained_at.utcoffset() is None:
            raise ValueError("model training timestamp must be timezone-aware")
        if not all(value.strip() for value in (name, version, feature_version)):
            raise ValueError("model name, version, and feature version are required")
        parsed = urlparse(artifact_uri)
        if parsed.scheme not in {"file", "s3", "mlflow-artifacts"} or not (
            parsed.netloc or parsed.path
        ):
            raise ValueError("model artifact URI must use an approved scheme")
        if len(artifact_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in artifact_sha256
        ):
            raise ValueError("model artifact SHA-256 must be lowercase hexadecimal")
        if any(
            not isinstance(value, (int, float)) or not isfinite(value) for value in metrics.values()
        ):
            raise ValueError("model metrics must be numeric")
        existing = await self.session.scalar(
            select(MLModelVersionRecord).where(
                MLModelVersionRecord.name == name, MLModelVersionRecord.version == version
            )
        )
        if existing is not None:
            candidate = self._domain(existing)
            if (
                candidate.feature_version != feature_version
                or candidate.trained_at != trained_at.astimezone(UTC)
                or candidate.artifact_uri != artifact_uri
                or candidate.artifact_sha256 != artifact_sha256
                or candidate.metrics != metrics
            ):
                raise ValueError("model version already exists with different metadata")
            return candidate
        record = MLModelVersionRecord(
            name=name,
            version=version,
            feature_version=feature_version,
            trained_at=trained_at,
            artifact_uri=artifact_uri,
            artifact_sha256=artifact_sha256,
            stage=ModelStage.CHALLENGER.value,
            metrics=metrics,
        )
        self.session.add(record)
        await self.session.flush()
        return self._domain(record)

    async def promote(self, model_id: UUID) -> RegisteredModel:
        record = await self.session.get(MLModelVersionRecord, model_id)
        if record is None:
            raise ValueError("model version does not exist")
        await self.session.execute(
            update(MLModelVersionRecord)
            .where(
                MLModelVersionRecord.name == record.name,
                MLModelVersionRecord.stage == ModelStage.CHAMPION.value,
                MLModelVersionRecord.id != model_id,
            )
            .values(stage=ModelStage.ARCHIVED.value)
        )
        record.stage = ModelStage.CHAMPION.value
        await self.session.flush()
        return self._domain(record)

    @staticmethod
    def _domain(record: MLModelVersionRecord) -> RegisteredModel:
        timestamp = (
            record.trained_at.replace(tzinfo=UTC)
            if record.trained_at.tzinfo is None
            else record.trained_at.astimezone(UTC)
        )
        return RegisteredModel(
            record.id,
            record.name,
            record.version,
            record.feature_version,
            timestamp,
            record.artifact_uri,
            record.artifact_sha256,
            ModelStage(record.stage),
            {key: float(value) for key, value in record.metrics.items()},
        )


class PredictionLogger:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def log(
        self,
        prediction: ModelPrediction,
        observation: FeatureObservation,
        *,
        model_id: UUID,
        instrument_id: UUID,
        data_snapshot_id: str,
    ) -> None:
        if observation.available_at > prediction.predicted_at:
            raise ValueError("prediction log contains future feature evidence")
        if not data_snapshot_id.strip():
            raise ValueError("prediction data snapshot ID is required")
        fingerprint_payload = {
            "values": observation.values,
            "available_at": observation.available_at.isoformat(),
            "model_id": str(model_id),
            "instrument_id": str(instrument_id),
            "snapshot": data_snapshot_id,
            "probability": prediction.probability,
            "predicted_at": prediction.predicted_at.isoformat(),
            "feature_version": prediction.feature_version,
        }
        fingerprint = sha256(
            json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        existing = await self.session.get(MLPredictionRecord, prediction.prediction_id)
        if existing is not None:
            if existing.input_fingerprint != fingerprint:
                raise ValueError("prediction ID already exists for different inputs")
            return
        self.session.add(
            MLPredictionRecord(
                id=prediction.prediction_id,
                model_id=model_id,
                instrument_id=instrument_id,
                predicted_at=prediction.predicted_at,
                probability=Decimal(str(prediction.probability)),
                feature_version=prediction.feature_version,
                data_snapshot_id=data_snapshot_id,
                input_fingerprint=fingerprint,
            )
        )
        await self.session.flush()
