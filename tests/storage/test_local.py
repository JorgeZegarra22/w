import hashlib
from io import BytesIO
from pathlib import Path

import pytest

from benter_peru.storage.local import (
    BlobDigestMismatchError,
    LocalBlobStore,
)


class UnreadableStream(BytesIO):
    def read(self, size: int = -1) -> bytes:
        raise AssertionError("existing blobs must not consume the repeated stream")


def test_repeated_hash_does_not_duplicate_or_rewrite_blob(tmp_path: Path) -> None:
    content = b"synthetic-pdf-content"
    digest = hashlib.sha256(content).hexdigest()
    store = LocalBlobStore(tmp_path / "blobs")

    first = store.put_if_absent(BytesIO(content), digest)
    target = tmp_path / "blobs" / digest
    original_mtime = target.stat().st_mtime_ns
    second = store.put_if_absent(UnreadableStream(b"different"), digest)

    assert first.created is True
    assert second.created is False
    assert first.sha256 == digest
    assert first.byte_size == len(content)
    assert first.storage_key == digest
    assert target.read_bytes() == content
    assert target.stat().st_mtime_ns == original_mtime
    assert [path.name for path in (tmp_path / "blobs").iterdir()] == [digest]


def test_rejects_stream_when_content_does_not_match_expected_hash(tmp_path: Path) -> None:
    store = LocalBlobStore(tmp_path / "blobs")

    with pytest.raises(BlobDigestMismatchError):
        store.put_if_absent(BytesIO(b"actual"), "0" * 64)

    assert list((tmp_path / "blobs").iterdir()) == []


def test_rejects_blob_directory_inside_repository() -> None:
    repository_root = Path.cwd().resolve()

    with pytest.raises(ValueError, match="outside the repository"):
        LocalBlobStore(repository_root / "var" / "blobs", repository_root=repository_root)
