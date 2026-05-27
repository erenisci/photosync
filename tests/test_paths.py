"""Tests for app.paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from app import paths


def test_get_app_root_in_dev_is_repo_root() -> None:
    # In development (not frozen) the root is the parent of app/.
    assert not paths.is_frozen()
    root = paths.get_app_root()
    assert (root / "app" / "paths.py").is_file()


def test_get_data_dir_is_created(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, "get_app_root", lambda: tmp_path)
    data_dir = paths.get_data_dir()
    assert data_dir == tmp_path / paths.DATA_DIRNAME
    assert data_dir.is_dir()


def test_derived_paths_live_under_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, "get_app_root", lambda: tmp_path)
    data_dir = tmp_path / paths.DATA_DIRNAME
    assert paths.get_settings_path() == data_dir / "settings.json"
    assert paths.get_db_path() == data_dir / "sync.db"
    assert paths.get_rclone_config_path() == data_dir / "rclone.conf"


def test_get_rclone_binary_missing_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, "get_app_root", lambda: tmp_path)
    with pytest.raises(FileNotFoundError):
        paths.get_rclone_binary()


def test_get_rclone_binary_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, "get_app_root", lambda: tmp_path)
    monkeypatch.setattr("platform.system", lambda: "Linux")
    bin_dir = tmp_path / paths.BIN_DIRNAME
    bin_dir.mkdir()
    (bin_dir / "rclone-linux").write_bytes(b"#!/bin/sh\n")
    assert paths.get_rclone_binary() == bin_dir / "rclone-linux"


def test_get_rclone_binary_unsupported_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("platform.system", lambda: "Plan9")
    with pytest.raises(RuntimeError):
        paths.get_rclone_binary()
