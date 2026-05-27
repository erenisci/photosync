"""Tests for app.rclone_client.

rclone itself is never invoked; subprocess.run / Popen are monkeypatched so we
verify argument construction, env handling, and output parsing.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from app import rclone_client
from app.rclone_client import RcloneClient, RcloneError, parse_progress_line


def _client(password: str | None = "secret") -> RcloneClient:
    return RcloneClient(
        binary=Path("/bin/rclone"),
        config_path=Path("/data/rclone.conf"),
        password=password,
    )


class _FakeCompleted:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# -- progress parsing -----------------------------------------------------


def test_parse_progress_line_full() -> None:
    line = "Transferred: 1.2 MiB / 5 MiB, 25%, 1.3 MiB/s, ETA 3s"
    assert parse_progress_line(line) == (25, "1.3 MiB/s")


def test_parse_progress_line_percent_only() -> None:
    assert parse_progress_line("... 100%") == (100, None)


def test_parse_progress_line_none() -> None:
    assert parse_progress_line("Checking files") == (None, None)


# -- argument & env construction -----------------------------------------


def test_run_includes_config_and_ask_password(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_run(cmd: list[str], **kwargs: Any) -> _FakeCompleted:
        seen["cmd"] = cmd
        seen["env"] = kwargs["env"]
        seen["shell"] = kwargs["shell"]
        return _FakeCompleted(returncode=0, stdout="ok")

    monkeypatch.setattr(subprocess, "run", fake_run)
    _client()._run(["lsd", "r:"])

    assert seen["shell"] is False
    assert "--config" in seen["cmd"] and str(Path("/data/rclone.conf")) in seen["cmd"]
    assert "--ask-password=false" in seen["cmd"]
    assert seen["env"]["RCLONE_CONFIG_PASS"] == "secret"


def test_run_omits_password_env_when_none(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, **kw: seen.update(env=kw["env"]) or _FakeCompleted(0),
    )
    _client(password=None)._run(["lsd", "r:"])
    assert "RCLONE_CONFIG_PASS" not in seen["env"]


def test_run_raises_on_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: _FakeCompleted(1, stderr="boom"))
    with pytest.raises(RcloneError) as exc:
        _client()._run(["lsd", "r:"])
    assert exc.value.returncode == 1
    assert "boom" in str(exc.value)


# -- high-level methods ---------------------------------------------------


def test_test_connection_true_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: _FakeCompleted(0))
    assert _client().test_connection("r") is True
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: _FakeCompleted(3))
    assert _client().test_connection("r") is False


def test_config_create_builds_key_value_args(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        subprocess, "run", lambda cmd, **kw: seen.update(cmd=cmd) or _FakeCompleted(0)
    )
    _client().config_create("myb2", "s3", {"provider": "Backblaze", "region": "us"})
    cmd = seen["cmd"]
    # Subcommand and name/type come first, then flattened key/value pairs.
    tail = cmd[cmd.index("config") :]
    assert tail == [
        "config",
        "create",
        "myb2",
        "s3",
        "provider",
        "Backblaze",
        "region",
        "us",
    ]


def test_authorize_parses_token(monkeypatch: pytest.MonkeyPatch) -> None:
    out = 'Now copy this:\n{"access_token": "abc", "expiry": "2026"}\nDone'
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: _FakeCompleted(0, stdout=out))
    token = _client().authorize("drive")
    assert token["access_token"] == "abc"


def test_list_remote_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    out = (
        '[{"Name": "a.jpg", "IsDir": false, "Hashes": {"SHA-256": "aaa"}},'
        ' {"Name": "sub", "IsDir": true},'
        ' {"Name": "b.jpg", "IsDir": false, "Hashes": {}}]'
    )
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: _FakeCompleted(0, stdout=out))
    assert _client().list_remote_hashes("r", "path") == {"aaa": "a.jpg"}


# -- copyto streaming -----------------------------------------------------


class _FakePopen:
    def __init__(self, lines: list[str], returncode: int = 0) -> None:
        self.stdout = iter(lines)
        self._rc = returncode

    def wait(self) -> int:
        return self._rc


def test_copyto_reports_progress(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    lines = ["Transferred: 0%\n", "Transferred: 50%, 2 MiB/s\n", "Transferred: 100%\n"]
    monkeypatch.setattr(rclone_client.subprocess, "Popen", lambda *a, **kw: _FakePopen(lines))
    seen: list[tuple[int | None, str | None]] = []
    _client().copyto(
        tmp_path / "x.jpg", "r", "dest/x.jpg", progress_cb=lambda p, s: seen.append((p, s))
    )
    assert seen == [(0, None), (50, "2 MiB/s"), (100, None)]


def test_copyto_raises_on_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        rclone_client.subprocess,
        "Popen",
        lambda *a, **kw: _FakePopen(["error\n"], returncode=1),
    )
    with pytest.raises(RcloneError):
        _client().copyto(tmp_path / "x.jpg", "r", "dest/x.jpg")
