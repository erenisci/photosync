"""Tests for app.scanner."""

from __future__ import annotations

from pathlib import Path

from app import scanner

# Minimal valid headers so has_media_signature passes.
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


def _write(path: Path, data: bytes = JPEG) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_finds_whitelisted_media(tmp_path: Path) -> None:
    _write(tmp_path / "a.jpg")
    _write(tmp_path / "sub" / "b.png", PNG)
    (tmp_path / "notes.txt").write_text("hi")
    found = {p.name for p in scanner.find_media_files(tmp_path)}
    assert found == {"a.jpg", "b.png"}


def test_skips_data_and_bin_dirs(tmp_path: Path) -> None:
    _write(tmp_path / "keep.jpg")
    _write(tmp_path / "data" / "ignored.jpg")
    _write(tmp_path / "bin" / "ignored2.jpg")
    found = {p.name for p in scanner.find_media_files(tmp_path)}
    assert found == {"keep.jpg"}


def test_skips_hidden_and_system_dirs(tmp_path: Path) -> None:
    _write(tmp_path / ".Trash" / "x.jpg")
    _write(tmp_path / "System Volume Information" / "y.jpg")
    _write(tmp_path / "visible.jpg")
    found = {p.name for p in scanner.find_media_files(tmp_path)}
    assert found == {"visible.jpg"}


def test_rejects_wrong_magic_bytes(tmp_path: Path) -> None:
    # .png extension but JPEG bytes -> no PNG signature match -> rejected.
    _write(tmp_path / "fake.png", JPEG)
    assert list(scanner.find_media_files(tmp_path)) == []


def test_accepts_extension_without_known_signature(tmp_path: Path) -> None:
    # RAW has no signature table entry, so extension alone is enough.
    _write(tmp_path / "shot.dng", b"\x00\x01\x02\x03random")
    found = {p.name for p in scanner.find_media_files(tmp_path)}
    assert found == {"shot.dng"}


def test_is_media_file_rejects_non_media(tmp_path: Path) -> None:
    txt = tmp_path / "f.txt"
    txt.write_text("x")
    assert not scanner.is_media_file(txt)


def test_video_extensions_recognized(tmp_path: Path) -> None:
    _write(tmp_path / "clip.mp4", b"\x00\x00\x00\x18ftypmp42")
    found = {p.name for p in scanner.find_media_files(tmp_path)}
    assert found == {"clip.mp4"}
