from __future__ import annotations

import asyncio
import ctypes
import ctypes.util
import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

import gi

gi.require_version("Gdk", "4.0")
from gi.repository import Gdk

LOGGER = logging.getLogger(__name__)

XKB_KEY_RETURN = 0xFF0D
XKB_KEY_TAB = 0xFF09
XKB_KEY_NO_SYMBOL = 0


class KeyboardSession(Protocol):
    async def open(self, restore_token: str | None) -> str | None: ...

    def send_keysym(self, keysym: int, pressed: bool) -> None: ...

    def close(self) -> None: ...


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


class KeysymConverter:
    def __init__(self, library: ctypes.CDLL | None = None) -> None:
        if library is None:
            library_name = ctypes.util.find_library("xkbcommon")
            if not library_name:
                raise RuntimeError("libxkbcommon was not found")
            library = ctypes.CDLL(library_name)
        self._library = library
        self._library.xkb_utf32_to_keysym.argtypes = [ctypes.c_uint32]
        self._library.xkb_utf32_to_keysym.restype = ctypes.c_uint32

    def convert(self, character: str) -> int:
        if character == "\n":
            return XKB_KEY_RETURN
        if character == "\t":
            return XKB_KEY_TAB
        if character == "\r":
            return XKB_KEY_NO_SYMBOL
        codepoint = ord(character)
        if codepoint < 0x20 or 0x7F <= codepoint < 0xA0:
            return XKB_KEY_NO_SYMBOL
        return int(self._library.xkb_utf32_to_keysym(codepoint))


class TextInjector:
    def __init__(
        self,
        keyboard: KeyboardSession,
        clipboard: Clipboard,
        converter: KeysymConverter | None = None,
        restore_token: str | None = None,
        on_restore_token: Callable[[str | None], None] | None = None,
    ) -> None:
        self.keyboard = keyboard
        self.clipboard = clipboard
        self.converter = converter or KeysymConverter()
        self.restore_token = restore_token
        self.on_restore_token = on_restore_token

    async def insert(self, text: str) -> InsertionOutcome:
        if not text:
            return InsertionOutcome(InsertionStatus.EMPTY)

        keysyms = [self.converter.convert(character) for character in text]
        if any(keysym == XKB_KEY_NO_SYMBOL for keysym in keysyms):
            self.clipboard.copy(text)
            return InsertionOutcome(InsertionStatus.COPIED)

        try:
            refreshed_token = await self.keyboard.open(self.restore_token)
        except Exception as error:
            LOGGER.warning("keyboard portal unavailable during insertion: %s", error)
            self._update_restore_token(None)
            self.clipboard.copy(text)
            return InsertionOutcome(InsertionStatus.COPIED)

        self._update_restore_token(refreshed_token)

        sent = 0
        events_sent = 0
        try:
            for keysym in keysyms:
                self.keyboard.send_keysym(keysym, True)
                events_sent += 1
                self.keyboard.send_keysym(keysym, False)
                events_sent += 1
                sent += 1
                if sent % 32 == 0:
                    await asyncio.sleep(0)
        except Exception:
            if events_sent == 0:
                self.clipboard.copy(text)
                return InsertionOutcome(InsertionStatus.COPIED)
            return InsertionOutcome(InsertionStatus.PARTIAL, sent)
        finally:
            self.keyboard.close()
        return InsertionOutcome(InsertionStatus.INSERTED, sent)

    def _update_restore_token(self, restore_token: str | None) -> None:
        self.restore_token = restore_token
        if self.on_restore_token is None:
            return
        try:
            self.on_restore_token(restore_token)
        except Exception as error:
            LOGGER.warning("could not persist keyboard portal permission: %s", error)
