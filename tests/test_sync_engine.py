"""Tests for app.sync_engine."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from app import sync_engine
from app.db import Database
from app.rclone_client import RcloneError

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF"


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database(tmp_path / "sync.db")
    yield database
    database.close()


class FakeRclone:
    """Records copyto calls; can be told to fail for specific files."""

    def __init__(self, fail_names: set[str] | None = None) -> None:
        self.uploaded: list[str] = []
        self.fail_names = fail_names or set()

    def copyto(self, local: Path, remote: str, remote_path: str, progress_cb=None) -> None:
        if local.name in self.fail_names:
            raise RcloneError(1, "simulated failure")
        self.uploaded.append(remote_path)


def _media(root: Path, name: str, data: bytes = JPEG) -> Path:
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def test_uploads_new_files(tmp_path: Path, db: Database) -> None:
    _media(tmp_path, "a.jpg")
    _media(tmp_path, "sub/b.jpg", JPEG + b"diff")
    rclone = FakeRclone()

    stats = sync_engine.sync(tmp_path, db, rclone, "r", "Backup")  # type: ignore[arg-type]

    assert stats.total == 2
    assert stats.uploaded == 2
    assert stats.skipped == 0
    assert set(rclone.uploaded) == {"Backup/a.jpg", "Backup/sub/b.jpg"}


def test_skips_already_uploaded_by_hash(tmp_path: Path, db: Database) -> None:
    _media(tmp_path, "a.jpg")
    rclone = FakeRclone()
    sync_engine.sync(tmp_path, db, rclone, "r", "Backup")  # type: ignore[arg-type]

    # Second run: same content -> recorded as uploaded -> skipped.
    rclone2 = FakeRclone()
    stats = sync_engine.sync(tmp_path, db, rclone2, "r", "Backup")  # type: ignore[arg-type]
    assert stats.skipped == 1
    assert stats.uploaded == 0
    assert rclone2.uploaded == []


def test_dedup_across_identical_content(tmp_path: Path, db: Database) -> None:
    # Same bytes, different names -> only the first uploads.
    _media(tmp_path, "one.jpg")
    _media(tmp_path, "two.jpg")
    rclone = FakeRclone()
    stats = sync_engine.sync(tmp_path, db, rclone, "r", "Backup")  # type: ignore[arg-type]
    assert stats.uploaded == 1
    assert stats.skipped == 1


def test_failure_is_counted_not_recorded(tmp_path: Path, db: Database) -> None:
    _media(tmp_path, "bad.jpg")
    rclone = FakeRclone(fail_names={"bad.jpg"})
    stats = sync_engine.sync(tmp_path, db, rclone, "r", "Backup")  # type: ignore[arg-type]
    assert stats.failed == 1
    assert stats.uploaded == 0
    assert stats.failures[0][0].name == "bad.jpg"
    # A failed upload must not be recorded, so a retry will try again.
    assert not db.is_uploaded(sync_engine.hasher.sha256_file(tmp_path / "bad.jpg"))


def test_match_percent(tmp_path: Path, db: Database) -> None:
    _media(tmp_path, "a.jpg")
    _media(tmp_path, "b.jpg", JPEG + b"x")
    sync_engine.sync(tmp_path, db, FakeRclone(), "r", "Backup")  # type: ignore[arg-type]
    stats = sync_engine.sync(tmp_path, db, FakeRclone(), "r", "Backup")  # type: ignore[arg-type]
    assert stats.match_percent == 100.0


def test_events_emitted(tmp_path: Path, db: Database) -> None:
    _media(tmp_path, "a.jpg")
    events: list[tuple[str, str]] = []
    sync_engine.sync(
        tmp_path,
        db,
        FakeRclone(),
        "r",
        "Backup",  # type: ignore[arg-type]
        on_event=lambda ev, p: events.append((ev, p.name)),
    )
    kinds = [ev for ev, _ in events]
    assert "hashing" in kinds and "uploading" in kinds and "uploaded" in kinds


def test_scan_cache_avoids_rehash(
    tmp_path: Path, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = _media(tmp_path, "a.jpg")
    sync_engine.sync(tmp_path, db, FakeRclone(), "r", "Backup")  # type: ignore[arg-type]

    # On the second run the cache should serve the hash; sha256_file must not run.
    def boom(*a: object, **k: object) -> str:
        raise AssertionError("re-hashed a cached file")

    monkeypatch.setattr(sync_engine.hasher, "sha256_file", boom)
    stats = sync_engine.sync(tmp_path, db, FakeRclone(), "r", "Backup")  # type: ignore[arg-type]
    assert stats.skipped == 1
    assert f.exists()
