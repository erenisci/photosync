"""Main sync window.

Displays:
  - Statistics header (total / uploaded / skipped / failed)
  - Current file + progress bar
  - Start / Stop button
  - Summary view after sync completes
"""

from __future__ import annotations

import threading
from pathlib import Path

import customtkinter as ctk

from app import paths
from app.config import Settings
from app.db import Database
from app.rclone_client import RcloneClient
from app.sync_engine import SyncStats, sync


class MainWindow(ctk.CTk):
    """PhotoSync sync screen."""

    def __init__(self, settings: Settings, password: str) -> None:
        super().__init__()
        self.title("PhotoSync")
        self.geometry("600x400")
        self.minsize(500, 350)

        self._settings = settings
        self._password = password
        self._running = False

        self._build_ui()

    def _build_ui(self) -> None:
        pad = {"padx": 20, "pady": 4}

        # ── Statistics ──────────────────────────────────────────────
        stats_frame = ctk.CTkFrame(self)
        stats_frame.pack(fill="x", **pad)

        self._lbl_total = ctk.CTkLabel(stats_frame, text="Total: —")
        self._lbl_total.pack(side="left", padx=10)
        self._lbl_uploaded = ctk.CTkLabel(stats_frame, text="Uploaded: 0")
        self._lbl_uploaded.pack(side="left", padx=10)
        self._lbl_skipped = ctk.CTkLabel(stats_frame, text="Skipped: 0")
        self._lbl_skipped.pack(side="left", padx=10)
        self._lbl_failed = ctk.CTkLabel(stats_frame, text="Failed: 0", text_color="red")
        self._lbl_failed.pack(side="left", padx=10)

        # ── Current file ────────────────────────────────────────────
        self._lbl_current = ctk.CTkLabel(self, text="Press Start to begin", anchor="w")
        self._lbl_current.pack(fill="x", **pad)

        self._progress = ctk.CTkProgressBar(self)
        self._progress.set(0)
        self._progress.pack(fill="x", **pad)

        # ── Match % ─────────────────────────────────────────────────
        self._lbl_match = ctk.CTkLabel(self, text="", font=("", 14))
        self._lbl_match.pack(**pad)

        # ── Buttons ─────────────────────────────────────────────────
        self._btn = ctk.CTkButton(self, text="▶  Start", command=self._toggle)
        self._btn.pack(pady=12)

        # ── Log area ────────────────────────────────────────────────
        self._log = ctk.CTkTextbox(self, height=120, state="disabled")
        self._log.pack(fill="both", expand=True, **pad)

    # ── actions ─────────────────────────────────────────────────────

    def _toggle(self) -> None:
        if self._running:
            return  # TODO Phase 2+: implement cancellation
        self._running = True
        self._btn.configure(state="disabled", text="Running…")
        threading.Thread(target=self._sync_worker, daemon=True).start()

    def _sync_worker(self) -> None:
        rclone = RcloneClient(
            binary=paths.get_rclone_binary(),
            config_path=paths.get_rclone_config_path(),
            password=self._password,
        )
        with Database() as db:
            stats = sync(
                root=paths.get_app_root(),
                db=db,
                rclone=rclone,
                remote=self._settings.remote_name,
                target_path=self._settings.target_path,
                on_event=self._on_event,
            )
        self.after(0, lambda: self._on_complete(stats))

    # ── callbacks (may arrive from worker thread) ───────────────────

    _ICONS = {
        "hashing": "🔑",
        "uploading": "⬆️",
        "uploaded": "✅",
        "skipped": "⏭️",
        "failed": "❌",
    }
    _counts = {"uploaded": 0, "skipped": 0, "failed": 0, "total": 0}

    def _on_event(self, event: str, path: Path) -> None:
        self.after(0, lambda: self._update_ui(event, path))

    def _update_ui(self, event: str, path: Path) -> None:
        icon = self._ICONS.get(event, "")
        self._lbl_current.configure(text=f"{icon} {event}: {path.name}")

        if event in ("uploaded", "skipped", "failed"):
            self._counts[event] += 1
        done = self._counts["uploaded"] + self._counts["skipped"] + self._counts["failed"]
        total = self._counts.get("total", 0)
        if total > 0:
            self._progress.set(done / total)

        self._lbl_uploaded.configure(text=f"Uploaded: {self._counts['uploaded']}")
        self._lbl_skipped.configure(text=f"Skipped: {self._counts['skipped']}")
        self._lbl_failed.configure(text=f"Failed: {self._counts['failed']}")

        self._append_log(f"{icon} {event:<10} {path.name}")

    def _on_complete(self, stats: SyncStats) -> None:
        self._lbl_total.configure(text=f"Total: {stats.total}")
        self._counts["total"] = stats.total
        self._progress.set(1.0)
        self._lbl_match.configure(text=f"Match: {stats.match_percent:.0f}%")
        self._lbl_current.configure(text="Sync complete!")
        self._btn.configure(state="normal", text="▶  Start")
        self._running = False

        summary = (
            f"\n{'=' * 40}\n"
            f"  Total:    {stats.total}\n"
            f"  Uploaded: {stats.uploaded}\n"
            f"  Skipped:  {stats.skipped} ({stats.match_percent:.0f}% match)\n"
            f"  Failed:   {stats.failed}\n"
            f"{'=' * 40}"
        )
        self._append_log(summary)

        if stats.failures:
            self._append_log("\nFailed files:")
            for p, reason in stats.failures:
                self._append_log(f"  {p.name}: {reason}")

    def _append_log(self, text: str) -> None:
        self._log.configure(state="normal")
        self._log.insert("end", text + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")
