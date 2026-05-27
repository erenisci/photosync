"""rclone subprocess wrapper.

Every rclone invocation in PhotoSync funnels through this module. Calls are made
with ``shell=False`` and an explicit argument list (never string interpolation)
to avoid injection, always with ``--config <path>`` and ``--ask-password=false``.
The master password is passed to rclone via the ``RCLONE_CONFIG_PASS``
environment variable for the duration of a single call and never persisted.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# progress_cb(percent, speed_text); percent may be None until rclone reports it.
ProgressCallback = Callable[[int | None, str | None], None]

# Matches the relevant fields of a `--progress --stats-one-line` line, e.g.
#   "Transferred: 1.234 MiB / 5.000 MiB, 25%, 1.234 MiB/s, ETA 3s"
_PROGRESS_RE = re.compile(r"(?P<percent>\d+)%(?:,\s*(?P<speed>[\d.]+\s*\w+/s))?")


class RcloneError(RuntimeError):
    """Raised when an rclone command exits with a non-zero status."""

    def __init__(self, returncode: int, stderr: str) -> None:
        self.returncode = returncode
        self.stderr = stderr.strip()
        super().__init__(f"rclone exited with {returncode}: {self.stderr}")


def parse_progress_line(line: str) -> tuple[int | None, str | None]:
    """Extract ``(percent, speed)`` from a single rclone progress line.

    Returns ``(None, None)`` for lines that carry no progress info.
    """
    match = _PROGRESS_RE.search(line)
    if match is None:
        return None, None
    percent = int(match.group("percent"))
    speed = match.group("speed")
    return percent, speed.strip() if speed else None


@dataclass
class RcloneClient:
    """Wraps a bundled rclone binary against a single config file."""

    binary: Path
    config_path: Path
    password: str | None = None

    def _base_args(self) -> list[str]:
        return [
            str(self.binary),
            "--config",
            str(self.config_path),
            "--ask-password=false",
        ]

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        if self.password:
            env["RCLONE_CONFIG_PASS"] = self.password
        else:
            env.pop("RCLONE_CONFIG_PASS", None)
        return env

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        """Run an rclone subcommand and return the completed process.

        Raises:
            RcloneError: if rclone exits non-zero.
        """
        proc = subprocess.run(  # noqa: S603 — fixed binary, arg list, shell=False
            self._base_args() + args,
            capture_output=True,
            text=True,
            env=self._env(),
            shell=False,
            check=False,
        )
        if proc.returncode != 0:
            raise RcloneError(proc.returncode, proc.stderr)
        return proc

    # -- connection / config ---------------------------------------------

    def test_connection(self, remote: str) -> bool:
        """Return ``True`` if ``rclone lsd <remote>:`` succeeds."""
        try:
            self._run(["lsd", f"{remote}:"])
        except RcloneError:
            return False
        return True

    def config_create(self, name: str, remote_type: str, params: dict[str, str]) -> None:
        """Create a remote via ``rclone config create``."""
        args = ["config", "create", name, remote_type]
        for key, value in params.items():
            args += [key, value]
        self._run(args)

    def authorize(self, remote_type: str) -> dict[str, object]:
        """Run ``rclone authorize <type>`` and return the parsed token dict.

        rclone opens a browser, captures the OAuth callback on localhost, and
        prints a JSON token blob to stdout on success.
        """
        proc = self._run(["authorize", remote_type])
        match = re.search(r"\{.*\}", proc.stdout, re.DOTALL)
        if match is None:
            raise RcloneError(0, "no token JSON found in rclone authorize output")
        parsed: dict[str, object] = json.loads(match.group(0))
        return parsed

    def list_remote_hashes(self, remote: str, path: str) -> dict[str, str]:
        """Return ``{sha256: filename}`` for files under ``remote:path``.

        Files whose hash rclone could not compute are skipped.
        """
        proc = self._run(["lsjson", f"{remote}:{path}", "--hash", "--hash-type", "SHA-256", "-R"])
        result: dict[str, str] = {}
        for entry in json.loads(proc.stdout or "[]"):
            if entry.get("IsDir"):
                continue
            digest = (entry.get("Hashes") or {}).get("SHA-256")
            if digest:
                result[digest] = entry.get("Name", "")
        return result

    # -- transfer --------------------------------------------------------

    def copyto(
        self,
        local: Path,
        remote: str,
        remote_path: str,
        progress_cb: ProgressCallback | None = None,
    ) -> None:
        """Upload a single file to ``remote:remote_path`` with live progress.

        Raises:
            RcloneError: if the transfer fails.
        """
        cmd = self._base_args() + [
            "copyto",
            str(local),
            f"{remote}:{remote_path}",
            "--progress",
            "--stats-one-line",
            "--stats",
            "0.5s",
        ]
        proc = subprocess.Popen(  # noqa: S603 — fixed binary, arg list, shell=False
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=self._env(),
            shell=False,
            bufsize=1,
        )
        assert proc.stdout is not None
        tail = ""
        for line in proc.stdout:
            tail = line
            if progress_cb is not None:
                percent, speed = parse_progress_line(line)
                if percent is not None:
                    progress_cb(percent, speed)
        returncode = proc.wait()
        if returncode != 0:
            raise RcloneError(returncode, tail)
