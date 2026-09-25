"""Checksum-verified byte artifact storage with no model deserialization."""

import os
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Protocol
from urllib.parse import quote, unquote, urlparse


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    uri: str
    sha256: str
    size_bytes: int


class ObjectArtifactClient(Protocol):
    """Minimal object-store capability; implementations must make create atomic."""

    def put_if_absent(self, bucket: str, key: str, payload: bytes) -> bool: ...

    def get(self, bucket: str, key: str, maximum_bytes: int) -> bytes: ...


class LocalArtifactStore:
    """Store opaque model bytes by digest; callers own safe serialization semantics."""

    def __init__(self, root: Path, *, maximum_size_bytes: int = 100_000_000) -> None:
        if maximum_size_bytes <= 0:
            raise ValueError("artifact maximum size must be positive")
        self.root = root.resolve()
        self.maximum_size_bytes = maximum_size_bytes
        self.root.mkdir(parents=True, exist_ok=True)

    def store(self, payload: bytes) -> ArtifactReference:
        if not payload or len(payload) > self.maximum_size_bytes:
            raise ValueError("artifact payload must be non-empty and within the size limit")
        digest = sha256(payload).hexdigest()
        destination = self.root / f"{digest}.artifact"
        if destination.exists():
            return self._verified_reference(destination, digest)
        with NamedTemporaryFile(dir=self.root, prefix=".artifact-", delete=False) as temporary:
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        try:
            os.link(temporary_path, destination)
        except FileExistsError:
            pass
        finally:
            temporary_path.unlink(missing_ok=True)
        return self._verified_reference(destination, digest)

    def load(self, reference: ArtifactReference) -> bytes:
        parsed = urlparse(reference.uri)
        if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
            raise ValueError("local artifact store requires a local file URI")
        path = Path(unquote(parsed.path))
        if path.is_symlink():
            raise ValueError("artifact path is outside the configured store")
        resolved = path.resolve(strict=True)
        if resolved.parent != self.root:
            raise ValueError("artifact path is outside the configured store")
        data = resolved.read_bytes()
        if len(data) != reference.size_bytes or len(data) > self.maximum_size_bytes:
            raise ValueError("artifact size does not match registered evidence")
        if sha256(data).hexdigest() != reference.sha256:
            raise ValueError("artifact checksum does not match registered evidence")
        return data

    def _verified_reference(self, path: Path, expected_digest: str) -> ArtifactReference:
        if path.is_symlink() or path.resolve().parent != self.root:
            raise ValueError("artifact path is outside the configured store")
        data = path.read_bytes()
        digest = sha256(data).hexdigest()
        if digest != expected_digest:
            raise ValueError("existing artifact content conflicts with its digest path")
        if len(data) > self.maximum_size_bytes:
            raise ValueError("existing artifact exceeds the size limit")
        return ArtifactReference(path.resolve().as_uri(), digest, len(data))


class RemoteArtifactStore:
    """Content-addressed opaque storage over an injected object-store client."""

    def __init__(
        self,
        client: ObjectArtifactClient,
        *,
        bucket: str,
        prefix: str = "models",
        maximum_size_bytes: int = 100_000_000,
    ) -> None:
        if (
            not 3 <= len(bucket) <= 63
            or bucket[0] not in "abcdefghijklmnopqrstuvwxyz0123456789"
            or bucket[-1] not in "abcdefghijklmnopqrstuvwxyz0123456789"
            or any(
                character not in "abcdefghijklmnopqrstuvwxyz0123456789.-" for character in bucket
            )
        ):
            raise ValueError("artifact bucket is invalid")
        if maximum_size_bytes <= 0:
            raise ValueError("artifact maximum size must be positive")
        normalized_prefix = prefix.strip("/")
        parts = normalized_prefix.split("/")
        if not normalized_prefix or any(
            part in {"", ".", ".."}
            or any(
                character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
                for character in part
            )
            for part in parts
        ):
            raise ValueError("artifact prefix is invalid")
        self.client = client
        self.bucket = bucket
        self.prefix = normalized_prefix
        self.maximum_size_bytes = maximum_size_bytes

    def store(self, payload: bytes) -> ArtifactReference:
        if not payload or len(payload) > self.maximum_size_bytes:
            raise ValueError("artifact payload must be non-empty and within the size limit")
        digest = sha256(payload).hexdigest()
        key = self._key(digest)
        created = self.client.put_if_absent(self.bucket, key, payload)
        if not created:
            existing = self.client.get(self.bucket, key, self.maximum_size_bytes)
            self._verify(existing, digest, len(payload))
        return ArtifactReference(self._uri(key), digest, len(payload))

    def load(self, reference: ArtifactReference) -> bytes:
        if len(reference.sha256) != 64 or any(
            character not in "0123456789abcdef" for character in reference.sha256
        ):
            raise ValueError("artifact checksum evidence is invalid")
        expected_key = self._key(reference.sha256)
        parsed = urlparse(reference.uri)
        if (
            parsed.scheme != "artifact+s3"
            or parsed.netloc != self.bucket
            or unquote(parsed.path).lstrip("/") != expected_key
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("artifact URI is outside the configured remote store")
        payload = self.client.get(self.bucket, expected_key, self.maximum_size_bytes)
        self._verify(payload, reference.sha256, reference.size_bytes)
        return payload

    def _key(self, digest: str) -> str:
        return f"{self.prefix}/{digest}.artifact"

    def _uri(self, key: str) -> str:
        return f"artifact+s3://{self.bucket}/{quote(key, safe='/')}"

    def _verify(self, payload: bytes, digest: str, size: int) -> None:
        if len(payload) != size or len(payload) > self.maximum_size_bytes:
            raise ValueError("artifact size does not match registered evidence")
        if sha256(payload).hexdigest() != digest:
            raise ValueError("artifact checksum does not match registered evidence")
