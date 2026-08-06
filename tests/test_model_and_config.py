from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path

from speaktext.config import Settings, SettingsStore
from speaktext.model import ModelManager


class SettingsTests(unittest.TestCase):
    def test_round_trip_and_private_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            store = SettingsStore(path)
            store.save(Settings("token", "toggle"))
            self.assertEqual(store.load(), Settings("token", "toggle"))
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)


class ModelTests(unittest.TestCase):
    def test_verifies_expected_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.bin"
            contents = b"model fixture"
            path.write_bytes(contents)
            digest = hashlib.sha256(contents).hexdigest()
            self.assertTrue(ModelManager(path, "unused", digest).verify())
            self.assertFalse(ModelManager(path, "unused", "0" * 64).verify())


if __name__ == "__main__":
    unittest.main()

