"""Google Drive provider."""

from __future__ import annotations

from app.providers.base import OAuthProvider


class GoogleDrive(OAuthProvider):
    def __init__(self) -> None:
        super().__init__(name="Google Drive", rclone_type="drive")
