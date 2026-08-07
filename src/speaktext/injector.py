from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

import gi

gi.require_version("Gdk", "4.0")
from gi.repository import Gdk  # noqa: E402


class Clipboard(Protocol):
    def copy(self, text: str) -> None: ...


class InsertionStatus(Enum):
    INSERTED = "inserted"
    COPIED = "copied"
    PARTIAL = "partial"
    EMPTY = "empty"


@dataclass(frozen=True, slots=True)
class InsertionOutcome:
    status: InsertionStatus
    sent_characters: int = 0


class ClipboardFallback:
    def copy(self, text: str) -> None:
        display = Gdk.Display.get_default()
        if display is None:
            raise RuntimeError("No graphical clipboard is available")
        display.get_clipboard().set_text(text)
