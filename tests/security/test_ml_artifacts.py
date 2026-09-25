from pathlib import Path

import pytest

from packages.machine_learning import ArtifactReference, LocalArtifactStore


def test_local_artifact_store_is_content_addressed_and_checksum_verified(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "models", maximum_size_bytes=1024)
    first = store.store(b'{"model":"logistic-v1"}')
    second = store.store(b'{"model":"logistic-v1"}')
    assert first == second
    assert store.load(first) == b'{"model":"logistic-v1"}'
    assert first.uri.startswith("file://")
    assert len(first.sha256) == 64

    Path(first.uri.removeprefix("file://")).write_bytes(b"tampered")
    with pytest.raises(ValueError, match=r"size|checksum"):
        store.load(first)
    with pytest.raises(ValueError, match="conflicts"):
        store.store(b'{"model":"logistic-v1"}')


def test_local_artifact_store_rejects_escape_symlink_and_oversize(
    tmp_path: Path,
) -> None:
    root = tmp_path / "models"
    store = LocalArtifactStore(root, maximum_size_bytes=8)
    outside = tmp_path / "outside.artifact"
    outside.write_bytes(b"outside")
    escaped = ArtifactReference(outside.as_uri(), "0" * 64, 7)
    with pytest.raises(ValueError, match="outside"):
        store.load(escaped)

    root.mkdir(exist_ok=True)
    link = root / "link.artifact"
    link.symlink_to(outside)
    linked = ArtifactReference(link.as_uri(), "0" * 64, 7)
    with pytest.raises(ValueError, match="outside"):
        store.load(linked)
    with pytest.raises(ValueError, match="size limit"):
        store.store(b"123456789")


def test_artifact_store_returns_bytes_without_deserializing(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "models")
    malicious_pickle_marker = b"cos\nsystem\n(S'echo unsafe'\ntR."
    reference = store.store(malicious_pickle_marker)
    assert store.load(reference) == malicious_pickle_marker
