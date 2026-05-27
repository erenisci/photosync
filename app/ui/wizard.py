"""First-run setup wizard.

Four screens:
  1. Choose cloud provider (radio buttons)
  2. Authenticate (OAuth browser flow or S3 credentials form)
  3. Pick the target path / bucket
  4. Create a master password

The wizard produces a :class:`~app.config.Settings` and a configured rclone
remote. It then hands control to the main sync window.
"""

from __future__ import annotations

import json
import threading

import customtkinter as ctk

from app import paths
from app.config import Settings, save_settings
from app.providers import ALL_PROVIDERS
from app.providers.base import CloudProvider, OAuthProvider
from app.providers.s3_compatible import PRESETS, S3Compatible
from app.rclone_client import RcloneClient
from app.ui.widgets import LabeledEntry, StatusLabel

_PAD_X = 24
_PAD_Y = 8


class WizardApp(ctk.CTk):
    """Runs the 4-screen setup flow and stores the result in :attr:`settings`."""

    def __init__(self) -> None:
        super().__init__()
        self.title("PhotoSync — Setup")
        self.geometry("520x440")
        self.resizable(False, False)

        self.settings: Settings | None = None
        self.password: str | None = None
        self._selected_provider: CloudProvider | None = None
        self._token_json: str | None = None
        self._rclone_params: dict[str, str] = {}

        self._container = ctk.CTkFrame(self)
        self._container.pack(fill="both", expand=True, padx=10, pady=10)

        self._show_step1()

    # ── Step 1 — Provider selection ────────────────────────────────────

    def _show_step1(self) -> None:
        self._clear()
        ctk.CTkLabel(
            self._container, text="Choose your cloud provider", font=("", 18, "bold")
        ).pack(pady=(16, 12))

        self._provider_var = ctk.StringVar(value="")
        for provider in ALL_PROVIDERS:
            ctk.CTkRadioButton(
                self._container,
                text=provider.name,
                variable=self._provider_var,
                value=provider.name,
            ).pack(anchor="w", padx=_PAD_X, pady=4)

        ctk.CTkButton(self._container, text="Next →", command=self._step1_next).pack(pady=(20, 8))

    def _step1_next(self) -> None:
        name = self._provider_var.get()
        for p in ALL_PROVIDERS:
            if p.name == name:
                self._selected_provider = p
                break
        if self._selected_provider is None:
            return  # nothing selected
        if isinstance(self._selected_provider, S3Compatible):
            self._show_step2_s3()
        else:
            self._show_step2_oauth()

    # ── Step 2a — OAuth ────────────────────────────────────────────────

    def _show_step2_oauth(self) -> None:
        assert isinstance(self._selected_provider, OAuthProvider)
        self._clear()
        ctk.CTkLabel(
            self._container,
            text=f"Authenticate with {self._selected_provider.name}",
            font=("", 18, "bold"),
        ).pack(pady=(16, 12))

        self._oauth_status = StatusLabel(self._container, text="")
        self._oauth_status.pack(pady=_PAD_Y)

        self._oauth_btn = ctk.CTkButton(
            self._container, text="Open browser to authorize", command=self._run_oauth
        )
        self._oauth_btn.pack(pady=_PAD_Y)

        self._next2 = ctk.CTkButton(
            self._container, text="Next →", command=self._step2_next, state="disabled"
        )
        self._next2.pack(pady=(20, 8))

    def _run_oauth(self) -> None:
        assert isinstance(self._selected_provider, OAuthProvider)
        self._oauth_btn.configure(state="disabled")
        self._oauth_status.set_info("Waiting for browser authorization…")
        provider = self._selected_provider

        def work() -> None:
            try:
                rclone = RcloneClient(
                    binary=paths.get_rclone_binary(),
                    config_path=paths.get_rclone_config_path(),
                )
                token = rclone.authorize(provider.rclone_type)
                self._token_json = json.dumps(token)
                self.after(0, lambda: self._oauth_done(True))
            except Exception as exc:
                msg = str(exc)
                self.after(0, lambda: self._oauth_done(False, msg))

        threading.Thread(target=work, daemon=True).start()

    def _oauth_done(self, ok: bool, error: str = "") -> None:
        if ok:
            self._oauth_status.set_ok("Connected!")
            self._next2.configure(state="normal")
        else:
            self._token_json = None  # Clear sensitive data on failure.
            self._oauth_status.set_error(f"Failed: {error}")
            self._oauth_btn.configure(state="normal")

    # ── Step 2b — S3 credentials ───────────────────────────────────────

    def _show_step2_s3(self) -> None:
        self._clear()
        ctk.CTkLabel(self._container, text="S3-compatible credentials", font=("", 18, "bold")).pack(
            pady=(16, 12)
        )

        frame = ctk.CTkFrame(self._container, fg_color="transparent")
        frame.pack(fill="x", padx=_PAD_X)

        # Preset dropdown
        ctk.CTkLabel(frame, text="Preset (optional)").pack(anchor="w")
        preset_names = ["(none)"] + list(PRESETS)
        self._s3_preset = ctk.CTkOptionMenu(
            frame, values=preset_names, command=self._apply_s3_preset
        )
        self._s3_preset.pack(fill="x", pady=(2, 6))

        self._s3_endpoint = LabeledEntry(frame, "Endpoint URL", placeholder="https://…")
        self._s3_endpoint.pack(fill="x", pady=2)
        self._s3_key = LabeledEntry(frame, "Access Key ID")
        self._s3_key.pack(fill="x", pady=2)
        self._s3_secret = LabeledEntry(frame, "Secret Access Key", show="•")
        self._s3_secret.pack(fill="x", pady=2)
        self._s3_region = LabeledEntry(frame, "Region", placeholder="us-east-1")
        self._s3_region.pack(fill="x", pady=2)

        self._s3_status = StatusLabel(self._container, text="")
        self._s3_status.pack(pady=4)

        btn_row = ctk.CTkFrame(self._container, fg_color="transparent")
        btn_row.pack(pady=(8, 8))
        ctk.CTkButton(btn_row, text="Test connection", command=self._test_s3).pack(
            side="left", padx=4
        )
        self._next2s3 = ctk.CTkButton(
            btn_row, text="Next →", command=self._step2_s3_next, state="disabled"
        )
        self._next2s3.pack(side="left", padx=4)

    def _apply_s3_preset(self, choice: str) -> None:
        preset = S3Compatible.apply_preset(choice)
        if preset.get("endpoint"):
            self._s3_endpoint.value = preset["endpoint"]

    def _test_s3(self) -> None:
        self._s3_status.set_info("Testing…")
        provider = S3Compatible(
            s3_provider=self._s3_preset.get() if self._s3_preset.get() != "(none)" else "Other",
            endpoint=self._s3_endpoint.value,
            access_key_id=self._s3_key.value,
            secret_access_key=self._s3_secret.value,
            region=self._s3_region.value,
        )
        self._rclone_params = provider.setup_params()

        def work() -> None:
            try:
                rclone = RcloneClient(
                    binary=paths.get_rclone_binary(),
                    config_path=paths.get_rclone_config_path(),
                )
                rclone.config_create("_test_s3", "s3", self._rclone_params)
                ok = rclone.test_connection("_test_s3")
                self.after(0, lambda: self._s3_test_done(ok))
            except Exception as exc:
                msg = str(exc)
                self.after(0, lambda: self._s3_test_done(False, msg))

        threading.Thread(target=work, daemon=True).start()

    def _s3_test_done(self, ok: bool, error: str = "") -> None:
        if ok:
            self._s3_status.set_ok("Connection OK!")
            self._next2s3.configure(state="normal")
        else:
            self._s3_status.set_error(f"Failed: {error}")

    def _step2_s3_next(self) -> None:
        self._show_step3()

    def _step2_next(self) -> None:
        self._show_step3()

    # ── Step 3 — Target path / bucket ──────────────────────────────────

    def _show_step3(self) -> None:
        assert self._selected_provider is not None
        self._clear()
        label_text = self._selected_provider.get_target_path_label()
        ctk.CTkLabel(
            self._container, text=f"Choose target {label_text.lower()}", font=("", 18, "bold")
        ).pack(pady=(16, 12))

        self._target = LabeledEntry(self._container, label_text, placeholder="PhotoSync/Backup")
        self._target.pack(fill="x", padx=_PAD_X, pady=_PAD_Y)
        self._target.value = "PhotoSync/Backup"

        ctk.CTkButton(self._container, text="Next →", command=self._step3_next).pack(pady=(20, 8))

    def _step3_next(self) -> None:
        if not self._target.value:
            return
        self._target_path = self._target.value
        self._show_step4()

    # ── Step 4 — Master password ───────────────────────────────────────

    def _show_step4(self) -> None:
        self._clear()
        ctk.CTkLabel(self._container, text="Create a master password", font=("", 18, "bold")).pack(
            pady=(16, 8)
        )
        ctk.CTkLabel(
            self._container,
            text="This encrypts your cloud access tokens.\nIf you lose it you must re-run setup.",
            text_color="gray",
            justify="center",
        ).pack(pady=(0, 10))

        self._pw1 = LabeledEntry(self._container, "Password", show="•")
        self._pw1.pack(fill="x", padx=_PAD_X, pady=4)
        self._pw2 = LabeledEntry(self._container, "Confirm password", show="•")
        self._pw2.pack(fill="x", padx=_PAD_X, pady=4)

        self._pw_status = StatusLabel(self._container, text="")
        self._pw_status.pack(pady=4)

        ctk.CTkButton(self._container, text="Finish ✓", command=self._finish).pack(pady=(16, 8))

    def _finish(self) -> None:
        pw1, pw2 = self._pw1.value, self._pw2.value
        if not pw1:
            self._pw_status.set_error("Password cannot be empty.")
            return
        if pw1 != pw2:
            self._pw_status.set_error("Passwords do not match.")
            return

        assert self._selected_provider is not None
        self.password = pw1
        remote_name = "photosync-remote"

        # Build rclone config params.
        if isinstance(self._selected_provider, OAuthProvider):
            params = self._selected_provider.setup_params(self._token_json)
        else:
            params = self._rclone_params

        # Persist.
        self._pw_status.set_info("Saving…")
        self.update()
        try:
            rclone = RcloneClient(
                binary=paths.get_rclone_binary(),
                config_path=paths.get_rclone_config_path(),
                password=pw1,
            )
            rclone.config_create(remote_name, self._selected_provider.rclone_type, params)
            self.settings = Settings(
                remote_name=remote_name,
                remote_type=self._selected_provider.rclone_type,
                target_path=self._target_path,
            )
            save_settings(self.settings)
            self._pw_status.set_ok("Done!")
            self.after(600, self.destroy)
        except Exception as exc:
            self._pw_status.set_error(f"Error: {exc}")

    # ── helpers ─────────────────────────────────────────────────────────

    def _clear(self) -> None:
        # Clear sensitive data between screens.
        self._rclone_params = {}
        for child in self._container.winfo_children():
            child.destroy()


def run_wizard() -> tuple[Settings | None, str | None]:
    """Launch the wizard and return ``(settings, password)`` or ``(None, None)``."""
    app = WizardApp()
    app.mainloop()
    return app.settings, app.password
