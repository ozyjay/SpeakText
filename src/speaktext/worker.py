from __future__ import annotations

import asyncio
import logging
import struct
from pathlib import Path

LOGGER = logging.getLogger(__name__)
MAX_TRANSCRIPT_BYTES = 16 * 1024 * 1024


class WorkerError(RuntimeError):
    pass


class TranscriptionWorker:
    def __init__(self, executable: Path, model_path: Path) -> None:
        self.executable = executable
        self.model_path = model_path
        self._process: asyncio.subprocess.Process | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    @property
    def ready(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def start(self) -> None:
        if self.ready:
            return
        if not self.executable.is_file():
            raise WorkerError(f"Transcription worker not found: {self.executable}")
        if not self.model_path.is_file():
            raise WorkerError(f"Model not found: {self.model_path}")

        process = await asyncio.create_subprocess_exec(
            str(self.executable),
            str(self.model_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            ready = await asyncio.wait_for(process.stdout.readline(), timeout=90)
        except asyncio.TimeoutError as error:
            process.kill()
            await process.wait()
            raise WorkerError("Timed out while loading the speech model") from error
        if ready != b"READY\n":
            detail = await self._read_error(process)
            raise WorkerError(detail or "Speech model failed to load")
        self._process = process
        self._stderr_task = asyncio.create_task(self._discard_stderr(process))
        LOGGER.info("transcription worker ready")

    async def transcribe(self, pcm: bytes) -> str:
        async with self._lock:
            if not self.ready:
                await self.start()
            process = self._process
            assert process is not None and process.stdin is not None
            assert process.stdout is not None

            try:
                process.stdin.write(struct.pack("<I", len(pcm)))
                process.stdin.write(pcm)
                await process.stdin.drain()
                size_raw = await asyncio.wait_for(
                    process.stdout.readexactly(4), timeout=120
                )
                size = struct.unpack("<I", size_raw)[0]
                if size > MAX_TRANSCRIPT_BYTES:
                    raise WorkerError("Worker returned an invalid transcript size")
                transcript = await asyncio.wait_for(
                    process.stdout.readexactly(size), timeout=10
                )
            except (BrokenPipeError, asyncio.IncompleteReadError, asyncio.TimeoutError) as error:
                if process.returncode is None:
                    process.kill()
                    await process.wait()
                self._process = None
                raise WorkerError("Transcription worker stopped or timed out") from error

            return transcript.decode("utf-8", errors="strict")

    async def stop(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        if process.returncode is None and process.stdin is not None:
            try:
                process.stdin.write(struct.pack("<I", 0))
                await process.stdin.drain()
                await asyncio.wait_for(process.wait(), timeout=3)
            except (BrokenPipeError, asyncio.TimeoutError):
                process.kill()
                await process.wait()
        if self._stderr_task is not None:
            await self._stderr_task
            self._stderr_task = None
        LOGGER.info("transcription worker stopped")

    @staticmethod
    async def _read_error(process: asyncio.subprocess.Process) -> str:
        if process.returncode is None:
            process.kill()
            await process.wait()
        if process.stderr is None:
            return ""
        return (await process.stderr.read()).decode("utf-8", errors="replace").strip()

    @staticmethod
    async def _discard_stderr(process: asyncio.subprocess.Process) -> None:
        if process.stderr is None:
            return
        while await process.stderr.read(4096):
            pass
