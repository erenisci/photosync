"""Cloud provider registry.

Import all concrete providers here so the wizard can enumerate them.
"""

from __future__ import annotations

from app.providers.base import CloudProvider, OAuthProvider
from app.providers.dropbox import Dropbox
from app.providers.google_drive import GoogleDrive
from app.providers.onedrive import OneDrive
from app.providers.s3_compatible import S3Compatible

# Ordered list used by the setup wizard to present radio buttons.
ALL_PROVIDERS: list[CloudProvider] = [
    GoogleDrive(),
    Dropbox(),
    OneDrive(),
    S3Compatible(),
]

__all__ = [
    "ALL_PROVIDERS",
    "CloudProvider",
    "Dropbox",
    "GoogleDrive",
    "OAuthProvider",
    "OneDrive",
    "S3Compatible",
]
