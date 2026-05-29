"""Filesystem location resolution.

PhotoSync ships as a PyInstaller ``--onefile`` bundle that lives on a USB flash
drive. Everything it reads or writes at runtime (settings, database, rclone
config, rclone binaries) is resolved relative to where the executable sits, so
the drive stays fully portable.

Two execution modes are supported:

* **Frozen** (``sys.frozen`` is set): the application was packaged with
  PyInstaller. ``sys.executable`` points at ``PhotoSync(.exe)`` on the USB
  drive, and the drive root is its parent directory.
* **Development** (running from source): the repository root is used instead.
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path

# Subdirectory (relative to the USB / project root) that holds runtime state.
DATA_DIRNAME = "data"
# Subdirectory that holds the bundled rclone binaries.
BIN_DIRNAME = "bin"
# Subdirectory holding the user's media to back up. Only files under this folder
# are scanned and uploaded; other folders on the drive are ignored. This gives
# the user explicit control over what leaves the drive.
SOURCE_DIRNAME = "PhotoSync"

# Per-platform rclone binary filenames as produced by scripts/download_rclone.py.
_RCLONE_BINARIES = {
    "Windows": "rclone.exe",
    "Darwin": "rclone-mac",
    "Linux": "rclone-linux",
}


def is_frozen() -> bool:
    """Return ``True`` when running from a PyInstaller bundle."""
    return getattr(sys, "frozen", False)


def get_app_root() -> Path:
    """Return the root directory PhotoSync operates from.

    When frozen this is the directory containing the executable (the USB drive
    root). In development it is the repository root (the parent of ``app/``).
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_data_dir() -> Path:
    """Return the runtime data directory, creating it if necessary."""
    data_dir = get_app_root() / DATA_DIRNAME
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_bin_dir() -> Path:
    """Return the directory containing the bundled rclone binaries."""
    return get_app_root() / BIN_DIRNAME


def get_source_dir() -> Path:
    """Return the user-content directory, creating it if necessary.

    Only files under this folder are scanned and uploaded by the sync engine.
    Everything else on the drive is left untouched.
    """
    source = get_app_root() / SOURCE_DIRNAME
    source.mkdir(parents=True, exist_ok=True)
    return source


def get_settings_path() -> Path:
    """Return the path to ``settings.json``."""
    return get_data_dir() / "settings.json"


def get_db_path() -> Path:
    """Return the path to the SQLite database."""
    return get_data_dir() / "sync.db"


def get_rclone_config_path() -> Path:
    """Return the path to the rclone config file."""
    return get_data_dir() / "rclone.conf"


def get_rclone_binary() -> Path:
    """Return the path to the rclone binary for the current platform.

    Raises:
        RuntimeError: if the current OS is unsupported.
        FileNotFoundError: if the expected binary is missing from ``bin/``.
    """
    system = platform.system()
    try:
        filename = _RCLONE_BINARIES[system]
    except KeyError as exc:
        raise RuntimeError(f"Unsupported platform: {system!r}") from exc

    binary = get_bin_dir() / filename
    if not binary.is_file():
        raise FileNotFoundError(
            f"rclone binary not found at {binary}. Run scripts/download_rclone.py to fetch it."
        )
    return binary
