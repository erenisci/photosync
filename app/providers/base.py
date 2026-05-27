"""Abstract cloud provider interface.

Each provider knows how to gather the rclone config parameters it needs (either
via an OAuth flow or a credentials form) and returns them as a plain dict that
the wizard feeds to :meth:`RcloneClient.config_create`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CloudProvider(ABC):
    """Base class for all cloud provider integrations."""

    name: str
    rclone_type: str

    @abstractmethod
    def setup_params(self, token_json: str | None = None) -> dict[str, str]:
        """Return rclone config ``key=value`` pairs for this provider.

        For OAuth providers *token_json* is the JSON blob returned by
        ``rclone authorize``. For S3-compatible providers it is ``None``; the
        implementation gathers credentials interactively or from pre-set values.
        """

    @abstractmethod
    def get_target_path_label(self) -> str:
        """Return the UI label for the target path field ("Folder", "Bucket", …)."""


class OAuthProvider(CloudProvider):
    """OAuth-based provider (Google Drive, Dropbox, OneDrive).

    ``rclone authorize <rclone_type>`` opens a browser, captures the callback
    on ``localhost:53682``, and prints a JSON token blob to stdout.
    """

    def setup_params(self, token_json: str | None = None) -> dict[str, str]:
        if not token_json:
            raise ValueError(f"token_json is required for {self.name}")
        return {"token": token_json}

    def get_target_path_label(self) -> str:
        return "Folder"
