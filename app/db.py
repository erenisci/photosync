"""SQLite persistence: upload history and scan cache.

Two tables back the deduplication logic:

* ``uploads`` — every file successfully uploaded, keyed by its SHA-256. This is
  the source of truth for "have I already uploaded this content?".
* ``scan_cache`` — maps an absolute path + ``(mtime_ns, size)`` to a previously
  computed SHA-256, so unchanged files are not re-hashed on every run.

The database lives on the USB flash drive, which may be slow at random writes,
so we run with ``PRAGMA synchronous = NORMAL`` (never ``FULL``).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import TracebackType

from app import paths
from app.config import _utcnow_iso

_SCHEMA = """
CREATE TABLE IF NOT EXISTS uploads (
    sha256       TEXT PRIMARY KEY,
    filename     TEXT NOT NULL,
    size_bytes   INTEGER NOT NULL,
    remote_path  TEXT NOT NULL,
    uploaded_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_filename ON uploads(filename);

CREATE TABLE IF NOT EXISTS scan_cache (
    abs_path      TEXT PRIMARY KEY,
    mtime_ns      INTEGER NOT NULL,
    size_bytes    INTEGER NOT NULL,
    sha256        TEXT NOT NULL,
    cached_at     TEXT NOT NULL
);
"""


class Database:
    """Thin wrapper over the PhotoSync SQLite database.

    Usable as a context manager::

        with Database() as db:
            if not db.is_uploaded(h):
                ...
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or paths.get_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        # USB-friendly durability: crash-safe enough, far faster than FULL.
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # -- upload history ---------------------------------------------------

    def is_uploaded(self, sha256: str) -> bool:
        """Return ``True`` if content with this hash was already uploaded."""
        row = self._conn.execute(
            "SELECT 1 FROM uploads WHERE sha256 = ? LIMIT 1", (sha256,)
        ).fetchone()
        return row is not None

    def record_upload(self, sha256: str, filename: str, size_bytes: int, remote_path: str) -> None:
        """Record a successful upload (idempotent on the hash key)."""
        self._conn.execute(
            """
            INSERT INTO uploads (sha256, filename, size_bytes, remote_path, uploaded_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(sha256) DO UPDATE SET
                filename = excluded.filename,
                size_bytes = excluded.size_bytes,
                remote_path = excluded.remote_path,
                uploaded_at = excluded.uploaded_at
            """,
            (sha256, filename, size_bytes, remote_path, _utcnow_iso()),
        )
        self._conn.commit()

    # -- scan cache -------------------------------------------------------

    def get_cached_hash(self, abs_path: str, mtime_ns: int, size_bytes: int) -> str | None:
        """Return the cached SHA-256 for a file if it is unchanged.

        A cache hit requires the path, modification time, and size to all match
        a previously stored entry; otherwise ``None`` is returned and the caller
        should re-hash.
        """
        row = self._conn.execute(
            """
            SELECT sha256 FROM scan_cache
            WHERE abs_path = ? AND mtime_ns = ? AND size_bytes = ?
            """,
            (abs_path, mtime_ns, size_bytes),
        ).fetchone()
        return row["sha256"] if row is not None else None

    def cache_hash(self, abs_path: str, mtime_ns: int, size_bytes: int, sha256: str) -> None:
        """Store (or refresh) the cached hash for a file path."""
        self._conn.execute(
            """
            INSERT INTO scan_cache (abs_path, mtime_ns, size_bytes, sha256, cached_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(abs_path) DO UPDATE SET
                mtime_ns = excluded.mtime_ns,
                size_bytes = excluded.size_bytes,
                sha256 = excluded.sha256,
                cached_at = excluded.cached_at
            """,
            (abs_path, mtime_ns, size_bytes, sha256, _utcnow_iso()),
        )
        self._conn.commit()

    # -- lifecycle --------------------------------------------------------

    def close(self) -> None:
        """Close the underlying connection."""
        self._conn.close()

    def __enter__(self) -> Database:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
