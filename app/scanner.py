"""Media file discovery on the USB drive.

``find_media_files`` walks the drive root and yields photo/video files, applying
an extension whitelist and a lightweight magic-byte sanity check. It deliberately
skips symlinks, hidden/system folders, and PhotoSync's own ``data/`` directory so
the tool never tries to back up its own database.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from app import paths

PHOTO_EXTENSIONS = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".heic",
        ".heif",
        ".gif",
        ".webp",
        ".bmp",
        ".tiff",
        ".tif",
        ".raw",
        ".cr2",
        ".nef",
        ".arw",
        ".dng",
    }
)
VIDEO_EXTENSIONS = frozenset(
    {
        ".mp4",
        ".mov",
        ".avi",
        ".mkv",
        ".webm",
        ".m4v",
        ".3gp",
        ".mpg",
        ".mpeg",
        ".wmv",
    }
)
MEDIA_EXTENSIONS = PHOTO_EXTENSIONS | VIDEO_EXTENSIONS

# Directory names that are never descended into. ``data`` is PhotoSync's own
# state folder; the rest are OS bookkeeping that should never be uploaded.
SKIP_DIR_NAMES = frozenset(
    {
        paths.DATA_DIRNAME,
        paths.BIN_DIRNAME,
        "System Volume Information",
        "$RECYCLE.BIN",
        ".Trash",
        ".Trashes",
        ".Spotlight-V100",
        ".fseventsd",
        "__pycache__",
    }
)

# Magic-byte signatures keyed by a family. Used as a best-effort sanity check:
# a file is rejected only when its extension implies a container we have a
# signature for AND none of that family's signatures match. Unknown families
# (e.g. RAW variants) are accepted on the extension alone.
_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".gif": (b"GIF87a", b"GIF89a"),
    ".bmp": (b"BM",),
    ".webp": (b"RIFF",),  # 'RIFF'....'WEBP'; prefix check is enough here
}


def _is_skippable_dir(name: str) -> bool:
    """Return ``True`` for hidden dirs and known OS/app bookkeeping folders."""
    return name in SKIP_DIR_NAMES or name.startswith(".")


def has_media_signature(path: Path, read_bytes: int = 16) -> bool:
    """Best-effort magic-byte check for an already-whitelisted file.

    Returns ``True`` when the file's leading bytes match a known signature for
    its extension family, or when we have no signature on file for that family
    (so formats like RAW pass on the extension alone). Unreadable files return
    ``False``.
    """
    sigs = _SIGNATURES.get(path.suffix.lower())
    if sigs is None:
        return True
    try:
        with path.open("rb") as fh:
            head = fh.read(read_bytes)
    except OSError:
        return False
    return any(head.startswith(sig) for sig in sigs)


def is_media_file(path: Path) -> bool:
    """Return ``True`` if ``path`` is a regular media file worth uploading."""
    if path.is_symlink() or not path.is_file():
        return False
    if path.suffix.lower() not in MEDIA_EXTENSIONS:
        return False
    return has_media_signature(path)


def find_media_files(root: Path) -> Iterator[Path]:
    """Yield media files under ``root``, depth-first, skipping junk directories.

    Symlinked directories are not followed (avoids cycles and escaping the
    drive). Files are filtered by :func:`is_media_file`.
    """
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if not _is_skippable_dir(entry.name):
                    stack.append(entry)
            elif is_media_file(entry):
                yield entry
