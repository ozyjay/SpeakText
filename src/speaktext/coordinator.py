from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from enum import Enum
from time import monotonic
from typing import Protocol

from .constants import MAX_RECORDING_SECONDS, MIN_RECORDING_SECONDS
from .injector import InsertionOutcome, InsertionStatus

LOGGER = logging.getLogger(__name__)
CONTROL_TOKEN = re.compile(r"<\|[^|]+\|>|\[(?:BLANK_AUDIO|NO_SPEECH|MUSIC)\]")


class DictationState(Enum):
    STARTING = "Starting"
    READY = "Ready"
    RECORDING = "Recording"
    TRANSCRIBING = "Transcribing"
    INSERTING = "Inserting"
    ERROR = "Error"


class Capture(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> bytes: ...

    async def cancel(self) -> None: ...


class Recogniser(Protocol):
    async def start(self) -> None: ...

    async def transcribe(self, pcm: bytes) -> str: ...

    async def stop(self) -> None: ...


class Injector(Protocol):
    async def insert(self, text: str) -> InsertionOutcome: ...


StateCallback = Callable[[DictationState, str], None]


def normalise_transcript(transcript: str) -> str:
    return CONTROL_TOKEN.sub("", transcript).strip()


class DictationCoordinator:
    def __init__(
        self,
        capture: Capture,
        recogniser: Recogniser,
        injector: Injector,
        on_state: StateCallback,
        max_recording_seconds: float = MAX_RECORDING_SECONDS,
        min_recording_seconds: float = MIN_RECORDING_SECONDS,
    ) -> None:
        self.capture = capture
        self.recogniser = recogniser
        self.injector = injector
        self.on_state = on_state
        self.max_recording_seconds = max_recording_seconds
        self.min_recording_seconds = min_recording_seconds
        self.state = DictationState.STARTING
        self.last_transcript: str | None = None
        self._recording_started = 0.0
        self._limit_task: asyncio.Task[None] | None = None
        self._operation_lock = asyncio.Lock()

    async def initialise(self) -> None:
        try:
            await self.recogniser.start()
        except Exception as error:
            self._fail(f"Could not start speech recognition: {error}", recover=False)
            raise
        self._set_state(DictationState.READY, "Double-tap Shift to dictate")

    async def activate(self) -> None:
        async with self._operation_lock:
            if self.state is not DictationState.READY:
                return
            try:
                await self.capture.start()
            except Exception as error:
                self._fail(f"Could not start the microphone: {error}")
                return
            self._recording_started = monotonic()
            self._set_state(DictationState.RECORDING, "Recording…")
            self._limit_task = asyncio.create_task(self._enforce_limit())

    async def deactivate(self) -> None:
        async with self._operation_lock:
            if self.state is not DictationState.RECORDING:
                return
            await self._finish_recording()

    async def cancel_recording(self) -> bool:
        async with self._operation_lock:
            if self.state is not DictationState.RECORDING:
                return False
            if self._limit_task:
                self._limit_task.cancel()
                self._limit_task = None
            try:
                await self.capture.cancel()
            except Exception as error:
                self._fail(f"Could not cancel microphone capture: {error}")
                return False
            self._set_state(DictationState.READY, "Recording cancelled")
            return True

    async def _finish_recording(self) -> None:
        if self._limit_task and self._limit_task is not asyncio.current_task():
            self._limit_task.cancel()
        self._limit_task = None
        duration = monotonic() - self._recording_started
        try:
            pcm = await self.capture.stop()
        except Exception as error:
            self._fail(f"Could not finish microphone capture: {error}")
            return
        if duration < self.min_recording_seconds or not pcm:
            self._set_state(DictationState.READY, "Recording was too short")
            return

        self._set_state(DictationState.TRANSCRIBING, "Transcribing…")
        try:
            transcript = normalise_transcript(await self.recogniser.transcribe(pcm))
        except Exception as error:
            self._fail(f"Transcription failed: {error}")
            return
        if not transcript:
            self._set_state(DictationState.READY, "No speech detected")
            return

        self._set_state(DictationState.INSERTING, "Inserting text…")
        outcome = await self.injector.insert(transcript)
        self._handle_outcome(transcript, outcome)

    def _handle_outcome(self, transcript: str, outcome: InsertionOutcome) -> None:
        if outcome.status is InsertionStatus.INSERTED:
            self.last_transcript = None
            self._set_state(DictationState.READY, "Text inserted")
        elif outcome.status is InsertionStatus.COPIED:
            self.last_transcript = transcript
            self._set_state(DictationState.READY, "Text copied; paste it at the cursor")
        elif outcome.status is InsertionStatus.PARTIAL:
            self.last_transcript = transcript
            self._fail("Insertion may be incomplete; the full transcript can be copied")
        else:
            self._set_state(DictationState.READY, "No speech detected")

    async def _enforce_limit(self) -> None:
        await asyncio.sleep(self.max_recording_seconds)
        async with self._operation_lock:
            if self.state is DictationState.RECORDING:
                await self._finish_recording()

    def copied_last_transcript(self) -> None:
        self.last_transcript = None
        if self.state is DictationState.ERROR:
            self._set_state(DictationState.READY, "Transcript copied")

    async def shutdown(self) -> None:
        if self._limit_task:
            self._limit_task.cancel()
        if self.state is DictationState.RECORDING:
            await self.capture.cancel()
        await self.recogniser.stop()

    def _fail(self, message: str, recover: bool = True) -> None:
        LOGGER.error("dictation error: %s", message)
        self._set_state(DictationState.ERROR, message)
        if recover:
            self._set_state(DictationState.READY, "Ready to try again")

    def _set_state(self, state: DictationState, message: str) -> None:
        self.state = state
        LOGGER.info("state=%s", state.value)
        self.on_state(state, message)
