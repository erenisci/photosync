"""Master password dialog shown at every launch.

Blocks the UI until the correct password is entered (or the user closes the
dialog, which exits the app). The password is returned as a plain ``str``
and stored only in memory.
"""

from __future__ import annotations

import customtkinter as ctk


class PasswordPrompt(ctk.CTkToplevel):
    """Modal dialog that asks for the rclone master password."""

    def __init__(self, master: ctk.CTk) -> None:
        super().__init__(master)
        self.title("PhotoSync — Master Password")
        self.geometry("380x180")
        self.resizable(False, False)
        self.result: str | None = None

        # Make modal.
        self.transient(master)
        self.grab_set()

        pad = {"padx": 20, "pady": (5, 0)}

        ctk.CTkLabel(
            self,
            text="Enter the master password to unlock\nyour cloud credentials.",
            justify="center",
        ).pack(pady=(18, 8))

        self._entry = ctk.CTkEntry(self, show="•", width=280)
        self._entry.pack(**pad)
        self._entry.bind("<Return>", lambda _: self._submit())
        self._entry.focus_set()

        self._error = ctk.CTkLabel(self, text="", text_color="red")
        self._error.pack(**pad)

        ctk.CTkButton(self, text="Unlock", command=self._submit).pack(pady=(8, 12))

        self.protocol("WM_DELETE_WINDOW", self._cancel)

    def _submit(self) -> None:
        value = self._entry.get().strip()
        if not value:
            self._error.configure(text="Password cannot be empty.")
            return
        self.result = value
        self.grab_release()
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.grab_release()
        self.destroy()


def ask_password(master: ctk.CTk) -> str | None:
    """Show a modal password dialog and return the entered password or ``None``."""
    dialog = PasswordPrompt(master)
    master.wait_window(dialog)
    return dialog.result
