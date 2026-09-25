from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database.base import Base
from packages.database.models import InstrumentRecord, MLModelVersionRecord
from packages.machine_learning import (
    FeatureObservation,
    ModelPrediction,
    ModelRegistry,
    ModelStage,
    PredictionLogger,
)


@pytest.mark.asyncio
async def test_registry_promotion_and_prediction_log_survive_restart() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime(2026, 9, 19, 5, tzinfo=UTC)
    instrument_id = uuid4()
    checksum = "a" * 64
    async with sessions() as session:
        session.add(
            InstrumentRecord(
                id=instrument_id,
                symbol="NIFTY",
                exchange="NSE",
                segment="INDEX",
                tick_size=Decimal("0.05"),
                lot_size=1,
                currency="INR",
                active=True,
            )
        )
        await session.flush()
        registry = ModelRegistry(session)
        first = await registry.register(
            name="direction",
            version="1",
            feature_version="features-v1",
            trained_at=now,
            artifact_uri="s3://models/direction/1",
            artifact_sha256=checksum,
            metrics={"brier": 0.2},
        )
        assert (await registry.promote(first.id)).stage is ModelStage.CHAMPION
        second = await registry.register(
            name="direction",
            version="2",
            feature_version="features-v1",
            trained_at=now + timedelta(minutes=1),
            artifact_uri="s3://models/direction/2",
            artifact_sha256="b" * 64,
            metrics={"brier": 0.1},
        )
        assert (await registry.promote(second.id)).stage is ModelStage.CHAMPION
        prediction = ModelPrediction(now, 0.7, "2", "features-v1")
        observation = FeatureObservation(now, (("momentum", 1.0),))
        logger = PredictionLogger(session)
        await logger.log(
            prediction,
            observation,
            model_id=second.id,
            instrument_id=instrument_id,
            data_snapshot_id="snapshot-1",
        )
        await logger.log(
            prediction,
            observation,
            model_id=second.id,
            instrument_id=instrument_id,
            data_snapshot_id="snapshot-1",
        )
        await session.commit()

    async with sessions() as session:
        first_record = await session.get(MLModelVersionRecord, first.id)
        assert first_record is not None
        assert first_record.stage == ModelStage.ARCHIVED.value
        registered = await ModelRegistry(session).register(
            name="direction",
            version="2",
            feature_version="features-v1",
            trained_at=now + timedelta(minutes=1),
            artifact_uri="s3://models/direction/2",
            artifact_sha256="b" * 64,
            metrics={"brier": 0.1},
        )
        assert registered.stage is ModelStage.CHAMPION
        with pytest.raises(ValueError, match="different inputs"):
            await PredictionLogger(session).log(
                prediction,
                FeatureObservation(now, (("momentum", -1.0),)),
                model_id=second.id,
                instrument_id=instrument_id,
                data_snapshot_id="snapshot-1",
            )
    await engine.dispose()
