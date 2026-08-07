from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from speaktext.model import ModelManager


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
