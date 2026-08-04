"""ZIP packaging + checksum helpers."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

from app.config import settings


def create_zip(zip_path: str | Path, members: list[tuple[str, str | Path]]) -> None:
    """Create a deflate-compressed ZIP.

    `members` is a list of (arcname, source_path). Files are read from disk while
    writing, so large CSVs are not held in memory.
    """
    level = settings.ZIP_COMPRESSION_LEVEL
    with zipfile.ZipFile(
        zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=level
    ) as zf:
        for arcname, source in members:
            zf.write(source, arcname)


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()
