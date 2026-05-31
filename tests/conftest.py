"""Shared pytest fixtures and helpers for PhotoSync tests."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PIL import Image

from app.db import Database


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    """A fresh SQLite-backed Database in a temp dir, closed after the test."""
    database = Database(tmp_path / "sync.db")
    yield database
    database.close()


def make_jpeg(path: Path, size: tuple[int, int] = (800, 600)) -> Path:
    """Write a Pillow-decodable JPEG at ``path`` and return it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color=(100, 150, 200)).save(path, format="JPEG", quality=90)
    return path
