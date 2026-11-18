"""Local immutable blob storage keyed by SHA-256."""

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import BinaryIO

SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
DEFAULT_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class StoredBlob:
    sha256: str
    byte_size: int
    storage_key: str
    created: bool


class BlobDigestMismatchError(ValueError):
    """Raised when stream bytes do not match the claimed SHA-256."""


class LocalBlobStore:
    """Publish immutable files outside the repository without overwriting."""

    def __init__(
        self, root: Path, *, repository_root: Path = DEFAULT_REPOSITORY_ROOT
    ) -> None:
        resolved_root = root.expanduser().resolve()
        resolved_repository = repository_root.expanduser().resolve()
        if resolved_root == resolved_repository or resolved_root.is_relative_to(
            resolved_repository
        ):
            raise ValueError("blob root must be outside the repository")
        resolved_root.mkdir(parents=True, exist_ok=True)
        self._root = resolved_root

    def put_if_absent(self, stream: BinaryIO, sha256: str) -> StoredBlob:
        """Verify and publish a stream only when its digest is not already stored."""
        if SHA256_PATTERN.fullmatch(sha256) is None:
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")

        target = self._root / sha256
        if target.is_file():
            return StoredBlob(sha256, target.stat().st_size, sha256, False)

        temporary_path: Path | None = None
        try:
            digest = hashlib.sha256()
            byte_size = 0
            with NamedTemporaryFile(
                mode="wb", dir=self._root, prefix=".tmp-", delete=False
            ) as temporary:
                temporary_path = Path(temporary.name)
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
                    byte_size += len(chunk)
                    temporary.write(chunk)
                temporary.flush()
                os.fsync(temporary.fileno())

            actual_digest = digest.hexdigest()
            if actual_digest != sha256:
                raise BlobDigestMismatchError(
                    f"expected SHA-256 {sha256}, received {actual_digest}"
                )

            try:
                if os.name == "nt":
                    os.rename(temporary_path, target)
                    temporary_path = None
                else:
                    os.link(temporary_path, target)
                created = True
            except FileExistsError:
                created = False
            return StoredBlob(sha256, target.stat().st_size, sha256, created)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
