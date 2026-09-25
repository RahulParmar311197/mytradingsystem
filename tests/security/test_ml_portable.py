import json
from datetime import UTC, datetime, timedelta

import pytest

from packages.machine_learning import (
    FeatureDefinition,
    FeatureObservation,
    PortableLogisticModel,
    train_logistic_baseline,
)

NOW = datetime(2026, 9, 20, 8, tzinfo=UTC)
DEFINITION = FeatureDefinition(("momentum", "volatility"), "features-v1")


def observations() -> tuple[FeatureObservation, ...]:
    return tuple(
        FeatureObservation(
            NOW + timedelta(minutes=index),
            (("momentum", float(index % 4)), ("volatility", float(index % 3))),
            index % 2,
        )
        for index in range(20)
    )


def portable_model() -> tuple[PortableLogisticModel, object]:
    baseline = train_logistic_baseline(
        observations(),
        DEFINITION,
        train_through=NOW + timedelta(minutes=14),
        validate_through=NOW + timedelta(minutes=19),
        model_version="logistic-v1",
    )
    return PortableLogisticModel.from_baseline(baseline), baseline


def test_portable_logistic_round_trip_matches_baseline_probability() -> None:
    portable, baseline = portable_model()
    reconstructed = PortableLogisticModel.from_bytes(portable.to_bytes())
    sample = FeatureObservation(
        NOW + timedelta(minutes=20), (("momentum", 2.0), ("volatility", 1.0))
    )
    expected = baseline.predict(sample, predicted_at=sample.available_at)
    actual = reconstructed.predict(sample, predicted_at=sample.available_at)
    assert actual.probability == pytest.approx(expected.probability, abs=1e-15)
    assert actual.model_version == expected.model_version
    assert reconstructed.to_bytes() == portable.to_bytes()


@pytest.mark.parametrize(
    "mutation",
    (
        lambda value: value.update(format="pickle-v1"),
        lambda value: value.update(scales=[1.0]),
        lambda value: value.update(intercept=float("inf")),
        lambda value: value.update(unexpected=True),
    ),
)
def test_portable_logistic_rejects_unsupported_or_invalid_documents(mutation: object) -> None:
    portable, _ = portable_model()
    document = json.loads(portable.to_bytes())
    mutation(document)  # type: ignore[operator]
    payload = json.dumps(document).encode()
    with pytest.raises(ValueError, match=r"unsupported|invalid"):
        PortableLogisticModel.from_bytes(payload)


def test_portable_logistic_never_accepts_pickle_or_future_features() -> None:
    with pytest.raises(ValueError, match="JSON"):
        PortableLogisticModel.from_bytes(b"cos\nsystem\n(S'echo unsafe'\ntR.")
    portable, _ = portable_model()
    sample = FeatureObservation(
        NOW + timedelta(minutes=21), (("momentum", 2.0), ("volatility", 1.0))
    )
    with pytest.raises(ValueError, match="unavailable"):
        portable.predict(sample, predicted_at=NOW + timedelta(minutes=20))


def test_portable_logistic_rejects_duplicate_fields_and_oversized_documents() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        PortableLogisticModel.from_bytes(b'{"format":"a","format":"b"}')
    with pytest.raises(ValueError, match="size"):
        PortableLogisticModel.from_bytes(b" " * 1_000_001)
