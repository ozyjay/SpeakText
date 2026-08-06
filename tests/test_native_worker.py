from __future__ import annotations

import os
import unittest
from pathlib import Path

from speaktext.worker import TranscriptionWorker


class NativeWorkerIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_loads_model_and_transcribes_silence(self) -> None:
        model_value = os.environ.get("SPEAKTEXT_TEST_MODEL")
        if not model_value:
            self.skipTest("SPEAKTEXT_TEST_MODEL is not set")
        worker_path = Path("build/speaktext-worker").resolve()
        if not worker_path.is_file():
            self.skipTest("native worker has not been built")

        worker = TranscriptionWorker(worker_path, Path(model_value))
        try:
            await worker.start()
            transcript = await worker.transcribe(bytes(32_000))
            self.assertIsInstance(transcript, str)
        finally:
            await worker.stop()


if __name__ == "__main__":
    unittest.main()

