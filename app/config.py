"""Application settings (``settings.json``) read/write.

The settings file records *non-secret* configuration only: which remote to use,
where to upload, and bookkeeping fields. Credentials and OAuth tokens are never
stored here — they live in the rclone config, encrypted with the user's master
password by rclone itself.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app import paths

# Current schema version. Bump when the on-disk shape changes and add migration
# handling in ``Settings.from_dict``.
SCHEMA_VERSION = 1


def _utcnow_iso() -> str:
    """Return the current UTC time as an ISO 8601 string with a ``Z`` suffix."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Settings:
    """User-facing PhotoSync settings persisted as ``settings.json``."""

    remote_name: str
    remote_type: str
    target_path: str
    version: int = SCHEMA_VERSION
    created_at: str = field(default_factory=_utcnow_iso)

    def to_dict(self) -> dict[str, object]:
        """Serialize to a plain dict suitable for JSON encoding."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Settings:
        """Build a ``Settings`` instance from decoded JSON.

        Raises:
            ValueError: if a required field is missing or the version is
                newer than this build understands.
        """
        version = int(str(data.get("version", SCHEMA_VERSION)))
        if version > SCHEMA_VERSION:
            raise ValueError(
                f"settings.json schema version {version} is newer than "
                f"supported version {SCHEMA_VERSION}; please update PhotoSync."
            )

        required = ("remote_name", "remote_type", "target_path")
        missing = [key for key in required if not data.get(key)]
        if missing:
            raise ValueError(f"settings.json is missing required field(s): {missing}")

        return cls(
            remote_name=str(data["remote_name"]),
            remote_type=str(data["remote_type"]),
            target_path=str(data["target_path"]),
            version=version,
            created_at=str(data.get("created_at") or _utcnow_iso()),
        )


def settings_exist(path: Path | None = None) -> bool:
    """Return ``True`` if a settings file is present (first-run detection)."""
    return (path or paths.get_settings_path()).is_file()


def load_settings(path: Path | None = None) -> Settings:
    """Load and validate settings from disk.

    Raises:
        FileNotFoundError: if the settings file does not exist.
        ValueError: if the file is malformed or invalid.
    """
    path = path or paths.get_settings_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FileNotFoundError(f"No settings file at {path}; run the setup wizard.") from None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"settings.json at {path} is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("settings.json must contain a JSON object.")
    return Settings.from_dict(data)


def save_settings(settings: Settings, path: Path | None = None) -> None:
    """Write settings to disk atomically (temp file + replace)."""
    path = path or paths.get_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(settings.to_dict(), indent=2, ensure_ascii=False)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)
