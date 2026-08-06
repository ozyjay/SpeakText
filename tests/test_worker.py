from __future__ import annotations

import os
import tempfile
import textwrap
import unittest
from pathlib import Path

from speaktext.worker import TranscriptionWorker


FAKE_WORKER = """\
#!/usr/bin/env python3
import struct
import sys

print("READY", flush=True)
while True:
    header = sys.stdin.buffer.read(4)
    if len(header) != 4:
        raise SystemExit(1)
    size = struct.unpack("<I", header)[0]
    if size == 0:
        raise SystemExit(0)
    payload = sys.stdin.buffer.read(size)
    if len(payload) != size:
        raise SystemExit(2)
    transcript = f"received {len(payload)} bytes".encode()
    sys.stdout.buffer.write(struct.pack("<I", len(transcript)) + transcript)
    sys.stdout.buffer.flush()
"""


class WorkerProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_framed_protocol_and_shutdown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "worker"
            executable.write_text(textwrap.dedent(FAKE_WORKER), encoding="utf-8")
            executable.chmod(0o755)
            model = root / "model.bin"
            model.write_bytes(b"fixture")

            worker = TranscriptionWorker(executable, model)
            await worker.start()
            self.assertEqual(await worker.transcribe(b"\x00\x01"), "received 2 bytes")
            await worker.stop()
            self.assertFalse(worker.ready)


if __name__ == "__main__":
    unittest.main()

