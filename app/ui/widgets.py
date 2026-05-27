"""Shared UI components built on CustomTkinter.

Small, reusable building blocks used across wizard screens and the main window.
"""

from __future__ import annotations

import customtkinter as ctk


class LabeledEntry(ctk.CTkFrame):
    """A label + entry combo with built-in getter/setter."""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        label: str,
        *,
        show: str = "",
        placeholder: str = "",
        **kwargs: object,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        ctk.CTkLabel(self, text=label, anchor="w").pack(fill="x")
        self._var = ctk.StringVar()
        entry_kwargs: dict[str, object] = {"textvariable": self._var}
        if show:
            entry_kwargs["show"] = show
        if placeholder:
            entry_kwargs["placeholder_text"] = placeholder
        ctk.CTkEntry(self, **entry_kwargs).pack(fill="x", pady=(2, 0))

    @property
    def value(self) -> str:
        return self._var.get().strip()

    @value.setter
    def value(self, v: str) -> None:
        self._var.set(v)


class StatusLabel(ctk.CTkLabel):
    """A label that blinks between OK (green) and error (red) states."""

    def set_ok(self, text: str) -> None:
        self.configure(text=text, text_color="green")

    def set_error(self, text: str) -> None:
        self.configure(text=text, text_color="red")

    def set_info(self, text: str) -> None:
        self.configure(text=text, text_color="gray")
