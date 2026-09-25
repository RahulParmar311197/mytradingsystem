"""Thin S3 SDK adapter for the vendor-neutral artifact client boundary."""

from collections.abc import Mapping
from typing import Any, Protocol


class S3SDKClient(Protocol):
    """Subset of a boto3-style client used by the adapter."""

    def put_object(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def get_object(self, **kwargs: Any) -> Mapping[str, Any]: ...


class S3ObjectArtifactClient:
    """Map artifact operations to S3 without constructing or configuring an SDK client."""

    def __init__(self, client: S3SDKClient) -> None:
        self.client = client

    def put_if_absent(self, bucket: str, key: str, payload: bytes) -> bool:
        try:
            self.client.put_object(
                Bucket=bucket,
                Key=key,
                Body=payload,
                ContentLength=len(payload),
                ContentType="application/octet-stream",
                IfNoneMatch="*",
                Metadata={"sha256": key.rsplit("/", 1)[-1].removesuffix(".artifact")},
            )
        except Exception as error:
            if _error_code(error) in {"412", "PreconditionFailed"}:
                return False
            raise
        return True

    def get(self, bucket: str, key: str, maximum_bytes: int) -> bytes:
        if maximum_bytes <= 0:
            raise ValueError("artifact read limit must be positive")
        response = self.client.get_object(Bucket=bucket, Key=key)
        body = response.get("Body")
        if body is None or not callable(getattr(body, "read", None)):
            raise ValueError("remote artifact response body is invalid")
        content_length = response.get("ContentLength")
        try:
            if (
                isinstance(content_length, bool)
                or not isinstance(content_length, int)
                or content_length < 0
                or content_length > maximum_bytes
            ):
                raise ValueError("remote artifact content length is invalid")
            payload = body.read(maximum_bytes + 1)
        finally:
            close = getattr(body, "close", None)
            if callable(close):
                close()
        if not isinstance(payload, bytes) or len(payload) != content_length:
            raise ValueError("remote artifact body does not match its content length")
        return payload


def _error_code(error: Exception) -> str | None:
    response = getattr(error, "response", None)
    if not isinstance(response, Mapping):
        return None
    details = response.get("Error")
    if not isinstance(details, Mapping):
        return None
    code = details.get("Code")
    return code if isinstance(code, str) else None
