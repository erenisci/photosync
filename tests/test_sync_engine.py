"""Tests for app.sync_engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from app import stub, sync_engine
from app.db import Database
from app.rclone_client import RcloneError
from tests.conftest import make_jpeg as _real_jpeg

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF"


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
    # type: ignore[arg-type]
    sync_engine.sync(tmp_path, db, rclone, "r", "Backup")

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


# ── Catalog mode ────────────────────────────────────────────────────────


def test_catalog_mode_replaces_original_with_stub(tmp_path: Path, db: Database) -> None:
    src = _real_jpeg(tmp_path / "photo.jpg", size=(1500, 1000))
    original_size = src.stat().st_size

    stats = sync_engine.sync(
        tmp_path,
        db,
        FakeRclone(),  # type: ignore[arg-type]
        "myremote",
        "Backup",
        mode="catalog",
    )

    assert stats.uploaded == 1
    assert src.exists()  # photo stub keeps the same path
    assert src.stat().st_size < original_size  # actually shrunk
    info = stub.parse_stub(src)
    assert info is not None
    assert info.url == "myremote:Backup/photo.jpg"


def test_catalog_mode_skips_existing_stubs(tmp_path: Path, db: Database) -> None:
    # File on drive is already a stub from a previous catalog sync — even if the
    # DB doesn't know about it, the EXIF marker should be enough.
    src = _real_jpeg(tmp_path / "old.jpg")
    src.write_bytes(stub.make_photo_stub(src, "myremote:Backup/old.jpg"))
    rclone = FakeRclone()

    stats = sync_engine.sync(
        tmp_path,
        db,
        rclone,
        "myremote",
        "Backup",
        mode="catalog",  # type: ignore[arg-type]
    )

    assert stats.skipped == 1
    assert stats.uploaded == 0
    assert rclone.uploaded == []


def test_catalog_mode_writes_index_html(tmp_path: Path, db: Database) -> None:
    _real_jpeg(tmp_path / "album" / "a.jpg")
    _real_jpeg(tmp_path / "album" / "b.jpg", size=(900, 700))

    sync_engine.sync(
        tmp_path,
        db,
        FakeRclone(),
        "r",
        "Backup",
        mode="catalog",  # type: ignore[arg-type]
    )

    folder_index = tmp_path / "album" / "index.html"
    root_index = tmp_path / "index.html"
    assert folder_index.is_file()
    assert root_index.is_file()
    text = folder_index.read_text(encoding="utf-8")
    assert "r:Backup/album/a.jpg" in text
    assert "r:Backup/album/b.jpg" in text


def test_backup_mode_leaves_originals_alone(tmp_path: Path, db: Database) -> None:
    src = _real_jpeg(tmp_path / "p.jpg", size=(1200, 900))
    original_size = src.stat().st_size

    sync_engine.sync(tmp_path, db, FakeRclone(), "r", "B")  # type: ignore[arg-type]

    assert src.stat().st_size == original_size  # untouched
    assert stub.parse_stub(src) is None  # not a stub
