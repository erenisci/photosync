"""OneDrive provider."""

from __future__ import annotations

from app.providers.base import OAuthProvider


class OneDrive(OAuthProvider):
    def __init__(self) -> None:
        super().__init__(name="OneDrive", rclone_type="onedrive")
