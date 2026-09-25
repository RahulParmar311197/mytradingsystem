from io import BytesIO
from typing import Any

import pytest

from packages.machine_learning import S3ObjectArtifactClient


class S3Error(Exception):
    def __init__(self, code: str) -> None:
        self.response = {"Error": {"Code": code}}


class FakeS3Client:
    def __init__(self) -> None:
        self.put_kwargs: dict[str, Any] | None = None
        self.get_kwargs: dict[str, Any] | None = None
        self.put_error: Exception | None = None
        self.response: dict[str, Any] = {"ContentLength": 4, "Body": BytesIO(b"data")}

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        self.put_kwargs = kwargs
        if self.put_error:
            raise self.put_error
        return {"ETag": "ignored"}

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        self.get_kwargs = kwargs
        return self.response


def test_s3_adapter_uses_conditional_create_without_owning_credentials() -> None:
    sdk = FakeS3Client()
    client = S3ObjectArtifactClient(sdk)
    assert client.put_if_absent("model-bucket", "models/abc.artifact", b"data")
    assert sdk.put_kwargs == {
        "Bucket": "model-bucket",
        "Key": "models/abc.artifact",
        "Body": b"data",
        "ContentLength": 4,
        "ContentType": "application/octet-stream",
        "IfNoneMatch": "*",
        "Metadata": {"sha256": "abc"},
    }


def test_s3_adapter_maps_only_precondition_failure_to_existing_object() -> None:
    sdk = FakeS3Client()
    client = S3ObjectArtifactClient(sdk)
    sdk.put_error = S3Error("PreconditionFailed")
    assert not client.put_if_absent("model-bucket", "models/abc.artifact", b"data")
    sdk.put_error = S3Error("AccessDenied")
    with pytest.raises(S3Error):
        client.put_if_absent("model-bucket", "models/abc.artifact", b"data")


def test_s3_adapter_bounds_reads_and_closes_response_body() -> None:
    sdk = FakeS3Client()
    body = BytesIO(b"data")
    sdk.response = {"ContentLength": 4, "Body": body}
    client = S3ObjectArtifactClient(sdk)
    assert client.get("model-bucket", "models/abc.artifact", 4) == b"data"
    assert sdk.get_kwargs == {"Bucket": "model-bucket", "Key": "models/abc.artifact"}
    assert body.closed


@pytest.mark.parametrize(
    "response",
    (
        {"ContentLength": 5, "Body": BytesIO(b"12345")},
        {"ContentLength": 4, "Body": BytesIO(b"bad")},
        {"ContentLength": "4", "Body": BytesIO(b"data")},
        {"ContentLength": 4, "Body": object()},
    ),
)
def test_s3_adapter_rejects_oversize_or_malformed_reads(response: dict[str, Any]) -> None:
    sdk = FakeS3Client()
    sdk.response = response
    with pytest.raises(ValueError, match=r"length|body"):
        S3ObjectArtifactClient(sdk).get("model-bucket", "models/abc.artifact", 4)
