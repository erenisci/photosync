"""Tests for app.db."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from app.db import Database


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database(tmp_path / "sync.db")
    yield database
    database.close()


def test_is_uploaded_false_then_true(db: Database) -> None:
    h = "a" * 64
    assert not db.is_uploaded(h)
    db.record_upload(h, "photo.jpg", 1234, "PhotoSync/Backup/photo.jpg")
    assert db.is_uploaded(h)


def test_record_upload_is_idempotent(db: Database) -> None:
    h = "b" * 64
    db.record_upload(h, "a.jpg", 10, "remote/a.jpg")
    db.record_upload(h, "a-renamed.jpg", 10, "remote/a-renamed.jpg")
    # Still a single row; second call updates rather than duplicates.
    assert db.is_uploaded(h)


def test_scan_cache_miss_then_hit(db: Database) -> None:
    path, mtime, size, h = "/x/img.jpg", 111, 2048, "c" * 64
    assert db.get_cached_hash(path, mtime, size) is None
    db.cache_hash(path, mtime, size, h)
    assert db.get_cached_hash(path, mtime, size) == h


def test_scan_cache_invalidated_on_mtime_change(db: Database) -> None:
    path, size, h = "/x/img.jpg", 2048, "d" * 64
    db.cache_hash(path, mtime_ns=100, size_bytes=size, sha256=h)
    assert db.get_cached_hash(path, 200, size) is None


def test_scan_cache_invalidated_on_size_change(db: Database) -> None:
    path, mtime, h = "/x/img.jpg", 100, "e" * 64
    db.cache_hash(path, mtime, size_bytes=2048, sha256=h)
    assert db.get_cached_hash(path, mtime, 4096) is None


def test_cache_hash_updates_existing_path(db: Database) -> None:
    path = "/x/img.jpg"
    db.cache_hash(path, 100, 2048, "f" * 64)
    db.cache_hash(path, 200, 4096, "0" * 64)
    assert db.get_cached_hash(path, 200, 4096) == "0" * 64
    assert db.get_cached_hash(path, 100, 2048) is None


def test_persists_across_connections(tmp_path: Path) -> None:
    db_path = tmp_path / "sync.db"
    h = "1" * 64
    with Database(db_path) as db:
        db.record_upload(h, "p.jpg", 1, "r/p.jpg")
    with Database(db_path) as db:
        assert db.is_uploaded(h)
