"""Core sync orchestrator.

Ties scanning, hashing, the scan cache, the upload history, and rclone together.
For the MVP this runs serially (no worker pool); per-file events are surfaced
through a callback so a CLI or GUI can render progress. Hash reuse via the scan
cache lives here, keeping :mod:`app.hasher` a pure function.

In *catalog* mode the engine replaces each successfully uploaded original with a
:mod:`app.stub` (thumbnail + cloud URL in EXIF), then records the *stub's* hash
in the uploads table so subsequent scans recognise the file as already-synced
and don't try to re-upload it.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from app import catalog, hasher, scanner, stub
from app.catalog import CatalogEntry
from app.config import SyncMode
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
#   event in {"hashing", "uploading", "skipped", "uploaded", "failed", "stubbed"}
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


def _record_stub(db: Database, stub_path: Path, remote_dest: str) -> None:
    """Hash the freshly written stub and record it so it's skipped on re-scan."""
    digest, size_bytes = _hash_with_cache(db, stub_path)
    db.record_upload(digest, stub_path.name, size_bytes, remote_dest)


def sync(
    root: Path,
    db: Database,
    rclone: RcloneClient,
    remote: str,
    target_path: str,
    files: Iterable[Path] | None = None,
    on_event: FileEventCallback | None = None,
    mode: SyncMode = "backup",
    remote_url_for: Callable[[str], str] | None = None,
) -> SyncStats:
    """Scan ``root`` and upload every media file not already in the cloud.

    Args:
        files: optional pre-scanned file list; defaults to scanning ``root``.
        on_event: optional per-file lifecycle callback.
        mode: ``"backup"`` keeps originals on the drive; ``"catalog"`` replaces
            each uploaded file with a thumbnail-with-URL stub.
        remote_url_for: catalog mode only — given a ``remote:path`` destination,
            return the URL to embed in the stub. Defaults to ``remote:path``.

    Returns:
        Aggregate :class:`SyncStats` for the session.
    """
    stats = SyncStats()

    def emit(event: str, path: Path) -> None:
        if on_event is not None:
            on_event(event, path)

    url_builder = remote_url_for or (lambda dest: f"{remote}:{dest}")

    file_list = list(files) if files is not None else list(scanner.find_media_files(root))
    stats.total = len(file_list)

    for path in file_list:
        try:
            # Catalog-mode safety net: if a file is already a stub but the DB
            # has been wiped, recognise it via its embedded marker and skip.
            if mode == "catalog" and stub.is_stub(path):
                stats.skipped += 1
                emit("skipped", path)
                continue

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

            if mode == "catalog":
                try:
                    stub_path = stub.write_stub(path, url_builder(dest))
                    _record_stub(db, stub_path, dest)
                    emit("stubbed", stub_path)
                except (OSError, ValueError) as exc:
                    logger.warning("Stub generation failed for %s: %s", path, exc)
        except (RcloneError, OSError) as exc:
            stats.failed += 1
            stats.failures.append((path, str(exc)))
            logger.warning("Upload failed for %s: %s", path, exc)
            emit("failed", path)

    # Catalog mode: walk the source dir once, pick up every stub (newly written
    # or pre-existing), and regenerate the HTML index pages. This way the
    # gallery is always complete, not just the diff from this run.
    if mode == "catalog":
        all_entries = _collect_existing_stubs(root)
        if all_entries:
            catalog.regenerate(root, all_entries)

    return stats


def _collect_existing_stubs(root: Path) -> list[CatalogEntry]:
    """Walk ``root`` and return a CatalogEntry for every PhotoSync stub found."""
    entries: list[CatalogEntry] = []
    for path in scanner.find_media_files(root):
        info = stub.parse_stub(path)
        if info is None:
            continue
        entries.append(
            CatalogEntry(
                thumbnail_path=path,
                cloud_url=info.url,
                original_name=info.original_name,
            )
        )
    return entries
