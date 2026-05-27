"""Core sync orchestrator.

Ties scanning, hashing, the scan cache, the upload history, and rclone together.
For the MVP this runs serially (no worker pool); per-file events are surfaced
through a callback so a CLI or GUI can render progress. Hash reuse via the scan
cache lives here, keeping :mod:`app.hasher` a pure function.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from app import hasher, scanner
from app.db import Database
from app.rclone_client import RcloneClient, RcloneError

logger = logging.getLogger(__name__)


@dataclass
class SyncStats:
    """Running tally of a sync session."""

    total: int = 0
    uploaded: int = 0
    skipped: int = 0
    failed: int = 0
    failures: list[tuple[Path, str]] = field(default_factory=list)

    @property
    def match_percent(self) -> float:
        """Share of scanned files already present in the cloud (skipped/total)."""
        return (self.skipped / self.total * 100) if self.total else 0.0


# Per-file lifecycle events for UI/CLI rendering.
#   event in {"hashing", "uploading", "skipped", "uploaded", "failed"}
FileEventCallback = Callable[[str, Path], None]


def _hash_with_cache(db: Database, path: Path) -> tuple[str, int]:
    """Return ``(sha256, size_bytes)`` reusing the scan cache when unchanged.

    The stat result is captured once and reused so that the size recorded for
    upload history matches the bytes that were actually hashed.
    """
    stat = path.stat()
    abs_path = str(path.resolve())
    cached = db.get_cached_hash(abs_path, stat.st_mtime_ns, stat.st_size)
    if cached is not None:
        return cached, stat.st_size
    digest = hasher.sha256_file(path)
    db.cache_hash(abs_path, stat.st_mtime_ns, stat.st_size, digest)
    return digest, stat.st_size


def _remote_path(target_path: str, local: Path, root: Path) -> str:
    """Build the remote destination path, preserving the drive-relative layout."""
    try:
        rel = local.resolve().relative_to(root.resolve())
    except ValueError:
        rel = Path(local.name)
    return f"{target_path.rstrip('/')}/{rel.as_posix()}"


def sync(
    root: Path,
    db: Database,
    rclone: RcloneClient,
    remote: str,
    target_path: str,
    files: Iterable[Path] | None = None,
    on_event: FileEventCallback | None = None,
) -> SyncStats:
    """Scan ``root`` and upload every media file not already in the cloud.

    Args:
        files: optional pre-scanned file list; defaults to scanning ``root``.
        on_event: optional per-file lifecycle callback.

    Returns:
        Aggregate :class:`SyncStats` for the session.
    """
    stats = SyncStats()

    def emit(event: str, path: Path) -> None:
        if on_event is not None:
            on_event(event, path)

    file_list = list(files) if files is not None else list(scanner.find_media_files(root))
    stats.total = len(file_list)

    for path in file_list:
        try:
            emit("hashing", path)
            digest, size_bytes = _hash_with_cache(db, path)

            if db.is_uploaded(digest):
                stats.skipped += 1
                emit("skipped", path)
                continue

            dest = _remote_path(target_path, path, root)
            emit("uploading", path)
            rclone.copyto(path, remote, dest)

            db.record_upload(digest, path.name, size_bytes, dest)
            stats.uploaded += 1
            emit("uploaded", path)
        except (RcloneError, OSError) as exc:
            stats.failed += 1
            stats.failures.append((path, str(exc)))
            logger.warning("Upload failed for %s: %s", path, exc)
            emit("failed", path)

    return stats
