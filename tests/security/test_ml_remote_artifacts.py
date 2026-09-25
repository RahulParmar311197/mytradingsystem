from dataclasses import replace

import pytest

from packages.machine_learning import RemoteArtifactStore


class MemoryObjectClient:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.puts = 0

    def put_if_absent(self, bucket: str, key: str, payload: bytes) -> bool:
        self.puts += 1
        identity = (bucket, key)
        if identity in self.objects:
            return False
        self.objects[identity] = payload
        return True

    def get(self, bucket: str, key: str, maximum_bytes: int) -> bytes:
        payload = self.objects[(bucket, key)]
        if len(payload) > maximum_bytes:
            raise ValueError("too large")
        return payload


def test_remote_artifact_store_is_content_addressed_and_idempotent() -> None:
    client = MemoryObjectClient()
    store = RemoteArtifactStore(client, bucket="research-models", prefix="team/models")
    first = store.store(b"portable model")
    second = store.store(b"portable model")
    assert first == second
    assert client.puts == 2
    assert len(client.objects) == 1
    assert first.uri.startswith("artifact+s3://research-models/team/models/")
    assert store.load(first) == b"portable model"


def test_remote_artifact_store_rejects_conflict_tampering_and_uri_escape() -> None:
    client = MemoryObjectClient()
    store = RemoteArtifactStore(client, bucket="research-models")
    reference = store.store(b"expected")
    identity = next(iter(client.objects))
    client.objects[identity] = b"tampered"
    with pytest.raises(ValueError, match=r"size|checksum"):
        store.load(reference)
    with pytest.raises(ValueError, match=r"size|checksum"):
        store.store(b"expected")
    with pytest.raises(ValueError, match="outside"):
        store.load(replace(reference, uri=reference.uri.replace("research-models", "other")))
    with pytest.raises(ValueError, match="outside"):
        store.load(replace(reference, uri=reference.uri + "?version=other"))


def test_remote_artifact_store_validates_configuration_and_evidence() -> None:
    client = MemoryObjectClient()
    with pytest.raises(ValueError, match="bucket"):
        RemoteArtifactStore(client, bucket="bad/bucket")
    with pytest.raises(ValueError, match="prefix"):
        RemoteArtifactStore(client, bucket="models", prefix="../models")
    store = RemoteArtifactStore(client, bucket="models", maximum_size_bytes=4)
    with pytest.raises(ValueError, match="size limit"):
        store.store(b"12345")
    reference = store.store(b"1234")
    with pytest.raises(ValueError, match="checksum evidence"):
        store.load(replace(reference, sha256="not-a-digest"))
