"""Tests for app.stub — photo stub generation, parsing, and round-trip."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from app import scanner, stub


def _make_photo(path: Path, size: tuple[int, int] = (2000, 1500)) -> Path:
    img = Image.new("RGB", size, color=(50, 120, 200))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="JPEG", quality=90)
    return path


def test_photo_stub_roundtrip(tmp_path: Path) -> None:
    src = _make_photo(tmp_path / "photo.jpg")
    url = "s3:bucket/PhotoSync/photo.jpg"
    stub_bytes = stub.make_photo_stub(src, url, max_size=512)

    out = tmp_path / "stub.jpg"
    out.write_bytes(stub_bytes)

    info = stub.parse_stub(out)
    assert info is not None
    assert info.url == url
    assert info.original_name == "photo.jpg"

    # Stub must be smaller than the original.
    assert out.stat().st_size < src.stat().st_size


def test_photo_stub_thumbnail_dimensions(tmp_path: Path) -> None:
    src = _make_photo(tmp_path / "big.jpg", size=(4000, 3000))
    stub_bytes = stub.make_photo_stub(src, "s3:r/big.jpg", max_size=512)

    out = tmp_path / "out.jpg"
    out.write_bytes(stub_bytes)
    with Image.open(out) as img:
        # thumbnail() preserves aspect, longest edge
        assert max(img.size) == 512


def test_parse_stub_returns_none_for_plain_jpeg(tmp_path: Path) -> None:
    src = _make_photo(tmp_path / "plain.jpg")
    assert stub.parse_stub(src) is None


def test_parse_stub_returns_none_for_non_jpeg(tmp_path: Path) -> None:
    p = tmp_path / "x.png"
    Image.new("RGB", (10, 10)).save(p, format="PNG")
    assert stub.parse_stub(p) is None


def test_is_stub_true_after_write(tmp_path: Path) -> None:
    src = _make_photo(tmp_path / "p.jpg")
    out = tmp_path / "p_stub.jpg"
    out.write_bytes(stub.make_photo_stub(src, "s3:r/p.jpg"))
    assert stub.is_stub(out)


def test_write_stub_photo_replaces_in_place(tmp_path: Path) -> None:
    src = _make_photo(tmp_path / "photo.jpg", size=(3000, 2000))
    orig_size = src.stat().st_size

    dest = stub.write_stub(src, "https://cloud.example/photo.jpg")

    assert dest == src  # photos keep their original path
    assert dest.exists()
    assert dest.stat().st_size < orig_size  # genuinely smaller
    info = stub.parse_stub(dest)
    assert info is not None
    assert info.url == "https://cloud.example/photo.jpg"


def test_write_stub_video_renames_and_deletes_original(tmp_path: Path) -> None:
    # Create a fake "video" file. Without ffmpeg, write_stub falls back to a
    # generic placeholder thumbnail, which is fine for this test.
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 4096)

    dest = stub.write_stub(video, "https://cloud.example/clip.mp4")

    assert dest.name == "clip.mp4.preview.jpg"
    assert dest.exists()
    assert not video.exists()  # original removed
    info = stub.parse_stub(dest)
    assert info is not None
    assert info.original_name == "clip.mp4"


def test_write_stub_rejects_unsupported_extension(tmp_path: Path) -> None:
    other = tmp_path / "doc.txt"
    other.write_text("hi")
    with pytest.raises(ValueError):
        stub.write_stub(other, "url")


def test_stub_destination_video_vs_photo(tmp_path: Path) -> None:
    photo = tmp_path / "img.jpg"
    photo.touch()
    assert stub.stub_destination(photo) == photo
    video = tmp_path / "vid.mp4"
    video.touch()
    assert stub.stub_destination(video) == tmp_path / ("vid.mp4" + stub.VIDEO_STUB_SUFFIX)


def test_stub_passes_scanner_signature_check(tmp_path: Path) -> None:
    # The stub must be a real JPEG so the scanner doesn't reject it on re-scan.
    src = _make_photo(tmp_path / "p.jpg")
    out = tmp_path / "p_stub.jpg"
    out.write_bytes(stub.make_photo_stub(src, "s3:r/p.jpg"))
    assert scanner.has_media_signature(out)
