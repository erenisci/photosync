"""Dropbox provider."""

from __future__ import annotations

from app.providers.base import OAuthProvider


class Dropbox(OAuthProvider):
    def __init__(self) -> None:
        super().__init__(name="Dropbox", rclone_type="dropbox")
