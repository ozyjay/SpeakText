from __future__ import annotations

import unittest

from speaktext.injector import (
    InsertionStatus,
    KeysymConverter,
    TextInjector,
    XKB_KEY_NO_SYMBOL,
    XKB_KEY_RETURN,
)


class FakeKeyboard:
    def __init__(
        self,
        fail_after: int | None = None,
        open_error: Exception | None = None,
        refreshed_token: str | None = "refreshed-token",
    ) -> None:
        self.fail_after = fail_after
        self.open_error = open_error
        self.refreshed_token = refreshed_token
        self.events: list[tuple[int, bool]] = []
        self.opened_with: list[str | None] = []
        self.close_count = 0

    async def open(self, restore_token: str | None) -> str | None:
        self.opened_with.append(restore_token)
        if self.open_error is not None:
            raise self.open_error
        return self.refreshed_token

    def send_keysym(self, keysym: int, pressed: bool) -> None:
        if self.fail_after is not None and len(self.events) >= self.fail_after:
            raise RuntimeError("portal failure")
        self.events.append((keysym, pressed))

    def close(self) -> None:
        self.close_count += 1


class FakeClipboard:
    def __init__(self) -> None:
        self.values: list[str] = []

    def copy(self, text: str) -> None:
        self.values.append(text)


class FakeConverter:
    def convert(self, character: str) -> int:
        return XKB_KEY_NO_SYMBOL if character == "\r" else ord(character)


class InjectorTests(unittest.IsolatedAsyncioTestCase):
    async def test_inserts_complete_text(self) -> None:
        keyboard = FakeKeyboard()
        clipboard = FakeClipboard()
        injector = TextInjector(keyboard, clipboard, FakeConverter())
        result = await injector.insert("abc")
        self.assertEqual(result.status, InsertionStatus.INSERTED)
        self.assertEqual(result.sent_characters, 3)
        self.assertEqual(len(keyboard.events), 6)
        self.assertEqual(keyboard.close_count, 1)
        self.assertEqual(clipboard.values, [])

    async def test_denied_keyboard_uses_clipboard(self) -> None:
        keyboard = FakeKeyboard(open_error=RuntimeError("permission denied"))
        clipboard = FakeClipboard()
        result = await TextInjector(keyboard, clipboard, FakeConverter()).insert("abc")
        self.assertEqual(result.status, InsertionStatus.COPIED)
        self.assertEqual(clipboard.values, ["abc"])

    async def test_unrepresentable_text_is_preflighted_before_insertion(self) -> None:
        keyboard = FakeKeyboard()
        clipboard = FakeClipboard()
        result = await TextInjector(keyboard, clipboard, FakeConverter()).insert("a\rb")
        self.assertEqual(result.status, InsertionStatus.COPIED)
        self.assertEqual(keyboard.events, [])
        self.assertEqual(keyboard.opened_with, [])
        self.assertEqual(keyboard.close_count, 0)

    async def test_partial_failure_does_not_duplicate_with_clipboard(self) -> None:
        keyboard = FakeKeyboard(fail_after=2)
        clipboard = FakeClipboard()
        result = await TextInjector(keyboard, clipboard, FakeConverter()).insert("abc")
        self.assertEqual(result.status, InsertionStatus.PARTIAL)
        self.assertEqual(result.sent_characters, 1)
        self.assertEqual(clipboard.values, [])
        self.assertEqual(keyboard.close_count, 1)

    async def test_failure_after_key_press_is_treated_as_partial(self) -> None:
        keyboard = FakeKeyboard(fail_after=1)
        clipboard = FakeClipboard()
        result = await TextInjector(keyboard, clipboard, FakeConverter()).insert("abc")
        self.assertEqual(result.status, InsertionStatus.PARTIAL)
        self.assertEqual(clipboard.values, [])
        self.assertEqual(keyboard.close_count, 1)

    async def test_refreshes_restore_token_for_each_on_demand_session(self) -> None:
        keyboard = FakeKeyboard(refreshed_token="new-token")
        updates: list[str | None] = []
        injector = TextInjector(
            keyboard,
            FakeClipboard(),
            FakeConverter(),
            restore_token="old-token",
            on_restore_token=updates.append,
        )

        await injector.insert("a")
        await injector.insert("b")

        self.assertEqual(keyboard.opened_with, ["old-token", "new-token"])
        self.assertEqual(keyboard.close_count, 2)
        self.assertEqual(updates, ["new-token", "new-token"])

    async def test_failed_session_clears_consumable_restore_token(self) -> None:
        keyboard = FakeKeyboard(open_error=RuntimeError("portal unavailable"))
        updates: list[str | None] = []
        injector = TextInjector(
            keyboard,
            FakeClipboard(),
            FakeConverter(),
            restore_token="single-use-token",
            on_restore_token=updates.append,
        )

        await injector.insert("a")

        self.assertIsNone(injector.restore_token)
        self.assertEqual(updates, [None])

    def test_real_converter_handles_unicode_and_newline(self) -> None:
        converter = KeysymConverter()
        self.assertNotEqual(converter.convert("é"), XKB_KEY_NO_SYMBOL)
        self.assertEqual(converter.convert("\n"), XKB_KEY_RETURN)
        self.assertEqual(converter.convert("\r"), XKB_KEY_NO_SYMBOL)


if __name__ == "__main__":
    unittest.main()
