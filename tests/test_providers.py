"""Tests for app.providers."""

from __future__ import annotations

import pytest

from app.providers import ALL_PROVIDERS, GoogleDrive, S3Compatible
from app.providers.base import OAuthProvider


def test_all_providers_registered() -> None:
    assert len(ALL_PROVIDERS) == 4
    names = [p.name for p in ALL_PROVIDERS]
    assert "Google Drive" in names
    assert "S3-compatible" in names


def test_oauth_requires_token() -> None:
    gd = GoogleDrive()
    with pytest.raises(ValueError):
        gd.setup_params(token_json=None)


def test_oauth_returns_token_param() -> None:
    gd = GoogleDrive()
    assert gd.setup_params('{"access_token":"x"}') == {"token": '{"access_token":"x"}'}


def test_oauth_providers_have_correct_types() -> None:
    for p in ALL_PROVIDERS:
        if isinstance(p, OAuthProvider):
            assert p.rclone_type in {"drive", "dropbox", "onedrive"}


def test_s3_setup_params() -> None:
    s3 = S3Compatible(
        s3_provider="B2",
        endpoint="https://s3.example.com",
        access_key_id="K",
        secret_access_key="S",
        region="us",
    )
    params = s3.setup_params()
    assert params["provider"] == "B2"
    assert params["endpoint"] == "https://s3.example.com"
    assert params["access_key_id"] == "K"
    assert params["env_auth"] == "false"


def test_s3_preset_backblaze() -> None:
    preset = S3Compatible.apply_preset("Backblaze B2")
    assert "backblaze" in preset["endpoint"].lower()
    assert preset["provider"] == "B2"


def test_s3_preset_unknown_returns_empty() -> None:
    assert S3Compatible.apply_preset("NoSuchCloud") == {}


def test_target_path_labels() -> None:
    assert GoogleDrive().get_target_path_label() == "Folder"
    assert S3Compatible().get_target_path_label() == "Bucket / key prefix"
