"""Private content-addressed local storage. No filenames supplied by clients become paths."""

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Protocol

from fastapi import HTTPException


class ArtifactStorage(Protocol):
    def path(self, key: str) -> Path: ...
    def publish(self, stream, limit: int) -> dict: ...


class LocalArtifactStorage:
    def __init__(self, root):
        self.root = Path(root)

    def path(self, key):
        if not re.fullmatch(r"[a-f0-9]{64}", key):
            raise ValueError("Invalid storage key")
        return self.root / key

    def publish(self, stream, limit):
        self.root.mkdir(parents=True, exist_ok=True)
        sha256, sha1, md5 = hashlib.sha256(), hashlib.sha1(), hashlib.md5(usedforsecurity=False)
        size = 0
        fd, temporary = tempfile.mkstemp(prefix=".upload-", dir=self.root)
        try:
            with os.fdopen(fd, "wb") as output:
                while chunk := stream.read(1024 * 1024):
                    size += len(chunk)
                    if size > limit:
                        raise HTTPException(413, "Firmware exceeds configured upload limit")
                    for digest in (sha256, sha1, md5):
                        digest.update(chunk)
                    output.write(chunk)
                if size == 0:
                    raise HTTPException(400, "Firmware file is empty")
                output.flush()
                os.fsync(output.fileno())
            key = sha256.hexdigest()
            try:
                # Same-filesystem hard link publishes atomically and never overwrites an object.
                os.link(temporary, self.path(key))
            except FileExistsError:
                with self.path(key).open("rb") as existing:
                    existing_hash = hashlib.file_digest(existing, "sha256").hexdigest()
                if existing_hash != key:
                    raise HTTPException(
                        503, "Stored artifact requires integrity inspection"
                    ) from None
            directory_fd = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return {
                "storage_key": key,
                "sha256": key,
                "sha1": sha1.hexdigest(),
                "md5": md5.hexdigest(),
                "size": size,
            }
        finally:
            Path(temporary).unlink(missing_ok=True)
