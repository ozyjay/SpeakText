from __future__ import annotations

import asyncio
import logging
import shutil
from collections.abc import Awaitable, Callable

from .constants import CHANNELS, SAMPLE_RATE

LOGGER = logging.getLogger(__name__)


class AudioCaptureError(RuntimeError):
    pass


class AudioCapture:
    """Capture raw mono s16 PCM from PipeWire without touching the filesystem."""

    def __init__(
        self,
        command: str = "pw-record",
        process_factory: Callable[..., Awaitable[asyncio.subprocess.Process]] | None = None,
    ) -> None:
        self.command = command
        self._process_factory = process_factory or asyncio.create_subprocess_exec
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[bytes] | None = None
        self._pcm = bytearray()

    @property
    def recording(self) -> bool:
        return self._process is not None

    async def start(self) -> None:
        if self.recording:
            raise AudioCaptureError("A recording is already active")
        if shutil.which(self.command) is None:
            raise AudioCaptureError(f"{self.command} was not found")

        process = await self._process_factory(
            self.command,
            "--media-category",
            "Capture",
            "--media-role",
            "Communication",
            "--rate",
            str(SAMPLE_RATE),
            "--channels",
            str(CHANNELS),
            "--format",
            "s16",
            "--raw",
            "-",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        if process.stdout is None:
            process.kill()
            raise AudioCaptureError("PipeWire capture did not expose an audio stream")

        self._pcm.clear()
        self._process = process
        self._reader_task = asyncio.create_task(self._read_pcm(process.stdout))
        LOGGER.info("audio capture started")

    async def _read_pcm(self, stream: asyncio.StreamReader) -> bytes:
        while chunk := await stream.read(4_096):
            self._pcm.extend(chunk)
        return bytes(self._pcm)

    def snapshot(self) -> bytes:
        """Return an in-memory copy suitable for provisional recognition."""
        if not self.recording:
            return b""
        return bytes(self._pcm)

    async def stop(self) -> bytes:
        process = self._process
        reader_task = self._reader_task
        if process is None or reader_task is None:
            raise AudioCaptureError("No recording is active")

        self._process = None
        self._reader_task = None
        if process.returncode is None:
            try:
                process.send_signal(2)  # SIGINT lets pw-record finish cleanly.
            except ProcessLookupError:
                pass

        try:
            await asyncio.wait_for(process.wait(), timeout=2)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()

        await reader_task
        pcm = bytes(self._pcm)
        self._pcm.clear()
        stderr = b""
        if process.stderr is not None:
            stderr = await process.stderr.read()
        if process.returncode not in (0, -2, 130) and not pcm:
            detail = stderr.decode("utf-8", errors="replace").strip()
            raise AudioCaptureError(detail or "PipeWire capture failed")

        LOGGER.info("audio capture stopped bytes=%d", len(pcm))
        return pcm

    async def cancel(self) -> None:
        process = self._process
        reader_task = self._reader_task
        self._process = None
        self._reader_task = None
        if process is not None and process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()
        if reader_task is not None:
            reader_task.cancel()
            await asyncio.gather(reader_task, return_exceptions=True)
        self._pcm.clear()
        LOGGER.info("audio capture cancelled")
