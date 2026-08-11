from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from speaktext.audio import AudioCapture


class Buffer:
    def __init__(self, value: bytes) -> None:
        self.value = value
        self._read = False

    async def read(self, _size: int = -1) -> bytes:
        if self._read:
            return b""
        self._read = True
        return self.value


class FakeProcess:
    def __init__(self) -> None:
        self.stdout = Buffer(b"\x01\x02")
        self.stderr = Buffer(b"")
        self.returncode: int | None = None
        self.signal: int | None = None

    def send_signal(self, signal: int) -> None:
        self.signal = signal
        self.returncode = -signal

    def kill(self) -> None:
        self.returncode = -9

    async def wait(self) -> int:
        self.returncode = 0 if self.returncode is None else self.returncode
        return self.returncode


class AudioCaptureTests(unittest.IsolatedAsyncioTestCase):
    async def test_records_pcm_to_memory(self) -> None:
        process = FakeProcess()
        arguments: list[object] = []

        async def factory(*args: object, **_kwargs: object) -> FakeProcess:
            arguments.extend(args)
            return process

        capture = AudioCapture("pw-record", factory)  # type: ignore[arg-type]
        with patch("speaktext.audio.shutil.which", return_value="/usr/bin/pw-record"):
            await capture.start()
            pcm = await capture.stop()

        self.assertEqual(pcm, b"\x01\x02")
        self.assertIn("--raw", arguments)
        self.assertIn("16000", arguments)
        self.assertEqual(process.signal, 2)


if __name__ == "__main__":
    unittest.main()
