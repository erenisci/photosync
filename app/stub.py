"""Catalog-mode stub generation.

When PhotoSync runs in *catalog* mode, the original photo/video is replaced on
the USB drive with a small stub that carries:

* A visible thumbnail so the file can still be previewed in any image viewer.
* The cloud URL of the original, embedded in the JPEG's EXIF UserComment.
* A magic marker (``PHOTOSYNC_STUB_V1``) so future scans can recognise the
  file as a stub and skip it instead of re-uploading.

For photos the stub keeps the original extension (``IMG_001.jpg`` stays
``IMG_001.jpg`` but becomes a 1024px thumbnail). For videos the file is
renamed to ``video.mp4.preview.jpg`` because viewers can't render a JPEG as
video — the user explicitly sees that the original lives in the cloud.

Video frame extraction relies on a bundled ``ffmpeg`` binary. When ffmpeg is
unavailable we fall back to a generic "Video" placeholder thumbnail; the URL
is preserved either way.
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from PIL.ExifTags import TAGS

from app import paths, scanner

logger = logging.getLogger(__name__)

# Marker stored in EXIF UserComment so we can recognise our stubs on re-scan.
STUB_MARKER = "PHOTOSYNC_STUB_V1"
# Suffix appended to video filenames when they are stubbed.
VIDEO_STUB_SUFFIX = ".preview.jpg"
# Default longest edge for thumbnails (pixels). Configurable per-call.
DEFAULT_THUMB_SIZE = 1024
# JPEG quality for stubs — high enough that previews look fine, low enough to be small.
DEFAULT_QUALITY = 85


@dataclass
class StubInfo:
    """Parsed metadata from a PhotoSync stub."""

    url: str
    original_name: str


def _ffmpeg_binary() -> Path | None:
    """Return the bundled ``ffmpeg`` binary path, or ``None`` if not present."""
    name = "ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg"
    candidate = paths.get_bin_dir() / name
    return candidate if candidate.is_file() else None


def _build_usercomment(url: str, original_name: str) -> bytes:
    """Build a UTF-8 encoded EXIF UserComment payload."""
    # EXIF UserComment must be prefixed with an 8-byte character-code identifier.
    # We use "UNICODE\0" so any compliant reader can decode the JSON below.
    payload = json.dumps(
        {"marker": STUB_MARKER, "url": url, "original_name": original_name},
        ensure_ascii=False,
    )
    return b"UNICODE\x00" + payload.encode("utf-16-be")


def _decode_usercomment(raw: bytes | str) -> str | None:
    """Reverse :func:`_build_usercomment`; return the JSON string or ``None``."""
    if isinstance(raw, str):
        candidate = raw
    else:
        if raw.startswith(b"UNICODE\x00"):
            try:
                candidate = raw[8:].decode("utf-16-be")
            except UnicodeDecodeError:
                return None
        elif raw.startswith(b"ASCII\x00\x00\x00"):
            candidate = raw[8:].decode("ascii", errors="replace")
        else:
            candidate = raw.decode("utf-8", errors="replace")
    return candidate if STUB_MARKER in candidate else None


# -- public API -----------------------------------------------------------


def parse_stub(path: Path) -> StubInfo | None:
    """Read EXIF from ``path`` and return :class:`StubInfo` if it is a stub.

    Returns ``None`` for non-JPEG files, files without EXIF, or files whose
    UserComment doesn't carry our marker. Errors are swallowed and logged.
    """
    if path.suffix.lower() not in {".jpg", ".jpeg"}:
        return None
    try:
        with Image.open(path) as img:
            exif = img.getexif()
    except (OSError, Image.UnidentifiedImageError):  # type: ignore[attr-defined]
        return None

    # UserComment is EXIF tag 0x9286 (37510).
    raw = exif.get(0x9286)
    if raw is None:
        # Some encoders put it in the ExifIFD subtree.
        ifd = exif.get_ifd(0x8769) if 0x8769 in exif else {}
        raw = ifd.get(0x9286)
    if raw is None:
        return None

    decoded = _decode_usercomment(raw)
    if decoded is None:
        return None
    try:
        data = json.loads(decoded)
    except json.JSONDecodeError:
        return None
    url = data.get("url")
    if not isinstance(url, str):
        return None
    return StubInfo(url=url, original_name=str(data.get("original_name", path.name)))


def is_stub(path: Path) -> bool:
    """Cheap predicate: does ``path`` look like a PhotoSync stub?"""
    return parse_stub(path) is not None


def make_photo_stub(
    source: Path,
    url: str,
    *,
    max_size: int = DEFAULT_THUMB_SIZE,
    quality: int = DEFAULT_QUALITY,
) -> bytes:
    """Return JPEG bytes containing a thumbnail of ``source`` + cloud URL in EXIF."""
    with Image.open(source) as original:
        thumb = original.convert("RGB")  # JPEG can't carry RGBA / palette.
        thumb.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

        exif = thumb.getexif()
        exif[0x9286] = _build_usercomment(url, source.name)

        buf = io.BytesIO()
        thumb.save(buf, format="JPEG", quality=quality, exif=exif.tobytes())
        return buf.getvalue()


def _extract_video_frame(source: Path, ffmpeg: Path, max_size: int) -> Image.Image | None:
    """Use ffmpeg to grab a representative frame and return it as a PIL image."""
    # Seek to 1 second to skip black title frames. ``-vframes 1`` grabs one frame.
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        cmd = [
            str(ffmpeg),
            "-y",
            "-ss",
            "1",
            "-i",
            str(source),
            "-vframes",
            "1",
            "-vf",
            f"scale='min({max_size},iw)':-2",
            str(tmp_path),
        ]
        result = subprocess.run(  # noqa: S603 — bundled binary, arg list, shell=False
            cmd,
            capture_output=True,
            shell=False,
            check=False,
            timeout=30,
        )
        if result.returncode != 0 or not tmp_path.is_file() or tmp_path.stat().st_size == 0:
            logger.warning("ffmpeg failed for %s: %s", source, result.stderr.decode("replace"))
            return None
        return Image.open(tmp_path).copy()
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)


def _placeholder_video_thumb(name: str, max_size: int) -> Image.Image:
    """Render a simple "Video" placeholder when ffmpeg isn't available."""
    img = Image.new("RGB", (max_size, max_size * 9 // 16), color=(30, 30, 30))
    draw = ImageDraw.Draw(img)
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont
    try:
        font = ImageFont.truetype("arial.ttf", max_size // 18)
    except OSError:
        font = ImageFont.load_default()
    text = f"▶  Video\n{name}"
    bbox = draw.multiline_textbbox((0, 0), text, font=font, align="center")
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.multiline_text(
        ((img.width - w) / 2, (img.height - h) / 2),
        text,
        fill=(220, 220, 220),
        font=font,
        align="center",
    )
    return img


def make_video_stub(
    source: Path,
    url: str,
    *,
    max_size: int = DEFAULT_THUMB_SIZE,
    quality: int = DEFAULT_QUALITY,
) -> bytes:
    """Return JPEG bytes for a video stub — a thumbnail frame plus the cloud URL."""
    ffmpeg = _ffmpeg_binary()
    img: Image.Image | None = None
    if ffmpeg is not None:
        img = _extract_video_frame(source, ffmpeg, max_size)
    if img is None:
        img = _placeholder_video_thumb(source.name, max_size)

    exif = img.getexif()
    exif[0x9286] = _build_usercomment(url, source.name)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, exif=exif.tobytes())
    return buf.getvalue()


def stub_destination(source: Path) -> Path:
    """Return the path the stub for ``source`` should be written to.

    Photos keep their original path. Videos get a ``.preview.jpg`` suffix so the
    user immediately sees the original is no longer on the drive.
    """
    suffix = source.suffix.lower()
    if suffix in scanner.VIDEO_EXTENSIONS:
        return source.with_name(source.name + VIDEO_STUB_SUFFIX)
    return source


def write_stub(source: Path, url: str, *, max_size: int = DEFAULT_THUMB_SIZE) -> Path:
    """Generate a stub for ``source`` and atomically replace the original.

    Returns the path of the resulting stub file. The original is deleted unless
    it's the same path (photos), in which case it's replaced atomically.
    """
    suffix = source.suffix.lower()
    if suffix in scanner.VIDEO_EXTENSIONS:
        stub_bytes = make_video_stub(source, url, max_size=max_size)
    elif suffix in scanner.PHOTO_EXTENSIONS:
        stub_bytes = make_photo_stub(source, url, max_size=max_size)
    else:
        raise ValueError(f"Unsupported file type for stub: {source.suffix}")

    dest = stub_destination(source)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(stub_bytes)
    tmp.replace(dest)

    # For videos: the original (.mp4 etc.) is now stale next to the new
    # .preview.jpg — delete it so the drive actually frees the space.
    if dest != source:
        try:
            source.unlink()
        except OSError as exc:
            logger.warning("Could not remove original video %s: %s", source, exc)
    return dest


# Re-export Exif tag id lookup for tests/debug convenience.
USER_COMMENT_TAG = next((tid for tid, name in TAGS.items() if name == "UserComment"), 0x9286)
