"""Chunked SHA-256 hashing.

Files on a USB drive can be large (multi-GB videos), so we hash in fixed-size
chunks and optionally report progress. The scan-cache reuse logic lives in
:mod:`app.sync_engine`; this module stays a pure, side-effect-free hasher so it
is trivial to test.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

# 1 MiB read chunks — a good balance for slow USB random reads.
DEFAULT_CHUNK_SIZE = 1024 * 1024

# Called as progress_cb(bytes_read, total_bytes). total may be 0 if unknown.
ProgressCallback = Callable[[int, int], None]


def sha256_file(
    path: Path,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    progress_cb: ProgressCallback | None = None,
) -> str:
    """Return the hex SHA-256 digest of ``path``, read in ``chunk_size`` chunks.

    If ``progress_cb`` is given it is invoked after each chunk with the number of
    bytes read so far and the total file size.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    total = path.stat().st_size
    digest = hashlib.sha256()
    read = 0
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
            read += len(chunk)
            if progress_cb is not None:
                progress_cb(read, total)
    return digest.hexdigest()
