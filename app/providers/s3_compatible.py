"""S3-compatible storage provider (Backblaze B2, Cloudflare R2, Wasabi, …).

Unlike OAuth providers this one collects access credentials directly. Popular
services have built-in presets that fill in the endpoint and provider field.
"""

from __future__ import annotations

from app.providers.base import CloudProvider

# Pre-filled endpoint URLs for popular S3-compatible services.
PRESETS: dict[str, dict[str, str]] = {
    "Backblaze B2": {
        "provider": "B2",
        "endpoint": "https://s3.us-west-004.backblazeb2.com",
    },
    "Cloudflare R2": {
        "provider": "Cloudflare",
        "endpoint": "",  # filled per account: https://<account-id>.r2.cloudflarestorage.com
    },
    "Wasabi": {
        "provider": "Wasabi",
        "endpoint": "https://s3.wasabisys.com",
    },
}


class S3Compatible(CloudProvider):
    """S3-compatible object storage."""

    def __init__(
        self,
        *,
        s3_provider: str = "Other",
        endpoint: str = "",
        access_key_id: str = "",
        secret_access_key: str = "",
        region: str = "",
    ) -> None:
        super().__init__(name="S3-compatible", rclone_type="s3")
        self.s3_provider = s3_provider
        self.endpoint = endpoint
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.region = region

    def setup_params(self, token_json: str | None = None) -> dict[str, str]:
        params: dict[str, str] = {
            "provider": self.s3_provider,
            "endpoint": self.endpoint,
            "env_auth": "false",
        }
        if self.access_key_id:
            params["access_key_id"] = self.access_key_id
        if self.secret_access_key:
            params["secret_access_key"] = self.secret_access_key
        if self.region:
            params["region"] = self.region
        return params

    def get_target_path_label(self) -> str:
        return "Bucket / key prefix"

    @staticmethod
    def apply_preset(preset_name: str) -> dict[str, str]:
        """Return the provider + endpoint for a named preset, or empty dict."""
        return dict(PRESETS.get(preset_name, {}))
