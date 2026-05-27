"""Tests for app.hasher."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app import hasher


def test_matches_hashlib(tmp_path: Path) -> None:
    data = b"photosync test payload" * 1000
    f = tmp_path / "f.bin"
    f.write_bytes(data)
    assert hasher.sha256_file(f) == hashlib.sha256(data).hexdigest()


def test_empty_file(tmp_path: Path) -> None:
    f = tmp_path / "empty.bin"
    f.write_bytes(b"")
    assert hasher.sha256_file(f) == hashlib.sha256(b"").hexdigest()


def test_small_chunk_size_same_result(tmp_path: Path) -> None:
    data = b"abcdefghij" * 50
    f = tmp_path / "f.bin"
    f.write_bytes(data)
    assert hasher.sha256_file(f, chunk_size=7) == hashlib.sha256(data).hexdigest()


def test_progress_callback_reports_total(tmp_path: Path) -> None:
    data = b"x" * 25
    f = tmp_path / "f.bin"
    f.write_bytes(data)
    calls: list[tuple[int, int]] = []
    hasher.sha256_file(f, chunk_size=10, progress_cb=lambda r, t: calls.append((r, t)))
    assert calls[-1] == (25, 25)
    assert [r for r, _ in calls] == [10, 20, 25]


def test_invalid_chunk_size(tmp_path: Path) -> None:
    f = tmp_path / "f.bin"
    f.write_bytes(b"x")
    with pytest.raises(ValueError):
        hasher.sha256_file(f, chunk_size=0)
