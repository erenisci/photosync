#!/usr/bin/env python3
"""PyInstaller build wrapper.

Produces a single ``PhotoSync`` executable that bundles the application and the
rclone binary for the current platform. Usage::

    python scripts/build.py               # build for the running OS
    python scripts/build.py --skip-rclone  # skip download_rclone step
"""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = REPO_ROOT / "bin"
DIST_DIR = REPO_ROOT / "dist"

# PyInstaller --add-data separator is `;` on Windows, `:` on Unix.
_DATA_SEP = ";" if platform.system() == "Windows" else ":"


def _ensure_rclone(skip: bool) -> None:
    """Download rclone binaries if not already present."""
    if skip:
        return
    script = REPO_ROOT / "scripts" / "download_rclone.py"
    target = {
        "Windows": "windows",
        "Darwin": "macos",
        "Linux": "linux",
    }.get(platform.system())
    if target is None:
        raise RuntimeError(f"Unsupported platform: {platform.system()}")
    cmd = [sys.executable, str(script), "--target", target]
    print(f"[build] Downloading rclone for {target}…")
    subprocess.run(cmd, check=True)


def _run_pyinstaller() -> Path:
    """Invoke PyInstaller and return the path to the built executable."""
    name = "PhotoSync"
    add_data = f"bin{_DATA_SEP}bin"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--windowed",
        f"--name={name}",
        f"--add-data={add_data}",
        str(REPO_ROOT / "app" / "main.py"),
    ]
    # Add icon if it exists.
    icon = REPO_ROOT / "assets" / "icon.ico"
    if icon.is_file():
        cmd.append(f"--icon={icon}")

    print(f"[build] {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=str(REPO_ROOT))

    suffix = ".exe" if platform.system() == "Windows" else ""
    exe = DIST_DIR / f"{name}{suffix}"
    if not exe.is_file():
        raise RuntimeError(f"Expected executable not found: {exe}")
    print(f"[build] Built {exe} ({exe.stat().st_size / 1024 / 1024:.1f} MB)")
    return exe


def _package_release(exe: Path) -> Path:
    """Create a release zip with the executable, README, and LICENSE."""
    import shutil

    system = platform.system().lower()
    version = "0.1.0"
    zip_name = f"PhotoSync-v{version}-{system}"
    staging = DIST_DIR / zip_name
    staging.mkdir(parents=True, exist_ok=True)

    shutil.copy2(exe, staging / exe.name)
    for name in ("LICENSE", "README.txt"):
        src = REPO_ROOT / name
        if src.is_file():
            shutil.copy2(src, staging / name)

    archive = shutil.make_archive(str(DIST_DIR / zip_name), "zip", DIST_DIR, zip_name)
    shutil.rmtree(staging)
    print(f"[build] Release archive: {archive}")
    return Path(archive)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build PhotoSync executable.")
    parser.add_argument("--skip-rclone", action="store_true", help="skip rclone download")
    parser.add_argument("--skip-package", action="store_true", help="skip release zip")
    args = parser.parse_args(argv)
    try:
        _ensure_rclone(args.skip_rclone)
        exe = _run_pyinstaller()
        if not args.skip_package:
            _package_release(exe)
    except Exception as exc:
        print(f"[build] error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
