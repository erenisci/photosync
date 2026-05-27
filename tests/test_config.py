"""Tests for app.config."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import (
    SCHEMA_VERSION,
    Settings,
    load_settings,
    save_settings,
    settings_exist,
)


def _sample() -> Settings:
    return Settings(
        remote_name="my-gdrive",
        remote_type="drive",
        target_path="PhotoSync/Backup",
    )


def test_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    original = _sample()
    save_settings(original, path)

    assert settings_exist(path)
    loaded = load_settings(path)
    assert loaded.remote_name == original.remote_name
    assert loaded.remote_type == original.remote_type
    assert loaded.target_path == original.target_path
    assert loaded.version == SCHEMA_VERSION
    assert loaded.created_at == original.created_at


def test_save_is_valid_json_with_expected_keys(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    save_settings(_sample(), path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data) == {
        "version",
        "remote_name",
        "remote_type",
        "target_path",
        "created_at",
    }


def test_settings_exist_false_when_missing(tmp_path: Path) -> None:
    assert not settings_exist(tmp_path / "nope.json")


def test_load_missing_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_settings(tmp_path / "nope.json")


def test_load_invalid_json_raises_value_error(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        load_settings(path)


def test_load_missing_required_field_raises(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"version": 1, "remote_name": "x"}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_settings(path)


def test_load_future_version_raises(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "version": SCHEMA_VERSION + 1,
                "remote_name": "x",
                "remote_type": "drive",
                "target_path": "p",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_settings(path)


def test_save_is_atomic_leaves_no_tmp(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    save_settings(_sample(), path)
    assert list(tmp_path.iterdir()) == [path]
