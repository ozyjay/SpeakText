from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from speaktext.settings import GestureKey, SettingsStore


class SettingsStoreTests(unittest.TestCase):
    def test_missing_setting_defaults_to_shift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "settings.ini")

            self.assertIs(store.load_gesture_key(), GestureKey.SHIFT)

    def test_gesture_key_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "settings.ini")

            store.save_gesture_key(GestureKey.CONTROL)

            self.assertIs(store.load_gesture_key(), GestureKey.CONTROL)

    def test_invalid_setting_defaults_to_shift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.ini"
            path.write_text(
                "[dictation]\ngesture_key = alt\n", encoding="utf-8"
            )

            self.assertIs(SettingsStore(path).load_gesture_key(), GestureKey.SHIFT)


if __name__ == "__main__":
    unittest.main()
