#!/usr/bin/env python3
"""Download pinned rclone binaries for all target platforms into ``bin/``.

rclone is bundled with PhotoSync rather than installed separately, so that the
USB drive is fully self-contained. The version is pinned (see ``RCLONE_VERSION``)
because we parse rclone's ``--progress`` output, which can change between
releases — bumping the pin is a deliberate, tested step.

Each download is verified against the official ``SHA256SUMS`` file before the
binary is extracted. Run from the repository root::

    python scripts/download_rclone.py
"""

from __future__ import annotations

import argparse
import hashlib
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

# Pinned rclone release. Bump deliberately and re-test progress parsing.
RCLONE_VERSION = "1.74.2"

BASE_URL = f"https://downloads.rclone.org/v{RCLONE_VERSION}"

# Maps a logical target -> (rclone archive slug, member binary name, output name).
# Output names match app.paths._RCLONE_BINARIES.
TARGETS: dict[str, tuple[str, str, str]] = {
    "windows": (f"rclone-v{RCLONE_VERSION}-windows-amd64", "rclone.exe", "rclone.exe"),
    "macos": (f"rclone-v{RCLONE_VERSION}-osx-amd64", "rclone", "rclone-mac"),
    "linux": (f"rclone-v{RCLONE_VERSION}-linux-amd64", "rclone", "rclone-linux"),
}

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"


def _fetch(url: str) -> bytes:
    print(f"  GET {url}")
    with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 (trusted host)
        data: bytes = resp.read()
    return data


def _load_checksums() -> dict[str, str]:
    """Return a mapping of archive filename -> expected SHA-256 hex digest."""
    text = _fetch(f"{BASE_URL}/SHA256SUMS").decode("utf-8")
    checksums: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, _, name = line.partition("  ")
        if name:
            checksums[name.strip()] = digest.strip().lower()
    return checksums


def _extract_member(archive: bytes, member_name: str) -> bytes:
    """Extract ``member_name`` from inside the (single-folder) rclone zip."""
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        for info in zf.infolist():
            if Path(info.filename).name == member_name and not info.is_dir():
                return zf.read(info)
    raise RuntimeError(f"{member_name!r} not found inside archive")


def download(target: str | None = None) -> None:
    """Download and verify binaries for ``target`` (or all targets)."""
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    checksums = _load_checksums()

    selected = {target: TARGETS[target]} if target else TARGETS
    for name, (slug, member, out_name) in selected.items():
        archive_filename = f"{slug}.zip"
        print(f"[{name}] {archive_filename}")
        archive = _fetch(f"{BASE_URL}/{archive_filename}")

        expected = checksums.get(archive_filename)
        if expected is None:
            raise RuntimeError(f"No checksum listed for {archive_filename}")
        actual = hashlib.sha256(archive).hexdigest()
        if actual != expected:
            raise RuntimeError(
                f"Checksum mismatch for {archive_filename}: expected {expected}, got {actual}"
            )
        print("  checksum OK")

        binary = _extract_member(archive, member)
        out_path = BIN_DIR / out_name
        out_path.write_bytes(binary)
        out_path.chmod(0o755)
        print(f"  wrote {out_path} ({len(binary):,} bytes)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download bundled rclone binaries.")
    parser.add_argument(
        "--target",
        choices=sorted(TARGETS),
        help="Download a single platform's binary (default: all).",
    )
    args = parser.parse_args(argv)
    try:
        download(args.target)
    except Exception as exc:  # noqa: BLE001 — surface a clean error to the build
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Done. rclone v{RCLONE_VERSION} binaries are in {BIN_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
