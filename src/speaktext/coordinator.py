from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from enum import Enum
from time import monotonic
from typing import Protocol

from .constants import (
    MAX_RECORDING_SECONDS,
    MIN_RECORDING_SECONDS,
    PREVIEW_INTERVAL_SECONDS,
)
from .injector import InsertionOutcome, InsertionStatus

LOGGER = logging.getLogger(__name__)
CONTROL_TOKEN = re.compile(r"<\|[^|]+\|>|\[(?:BLANK_AUDIO|NO_SPEECH|MUSIC)\]")


class DictationState(Enum):
    STARTING = "Starting"
    READY = "Ready"
    RECORDING = "Recording"
    TRANSCRIBING = "Transcribing"
    REVIEWING = "Reviewing"
    INSERTING = "Inserting"
    ERROR = "Error"


class Capture(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> bytes: ...

    async def cancel(self) -> None: ...

    def snapshot(self) -> bytes: ...


class Recogniser(Protocol):
    async def start(self) -> None: ...

    async def transcribe(self, pcm: bytes) -> str: ...

    async def stop(self) -> None: ...


class Injector(Protocol):
    async def insert(self, text: str) -> InsertionOutcome: ...


StateCallback = Callable[[DictationState, str], None]
TestTranscriptCallback = Callable[[str], None]
PreviewCallback = Callable[[str], None]


def normalise_transcript(transcript: str) -> str:
    return CONTROL_TOKEN.sub("", transcript).strip()


class DictationCoordinator:
    def __init__(
        self,
        capture: Capture,
        recogniser: Recogniser,
        injector: Injector,
        on_state: StateCallback,
        on_test_transcript: TestTranscriptCallback | None = None,
        on_preview: PreviewCallback | None = None,
        on_clear_preview: Callable[[], None] | None = None,
        gesture_label: str = "Shift",
        max_recording_seconds: float = MAX_RECORDING_SECONDS,
        min_recording_seconds: float = MIN_RECORDING_SECONDS,
        preview_interval_seconds: float = PREVIEW_INTERVAL_SECONDS,
    ) -> None:
        self.capture = capture
        self.recogniser = recogniser
        self.injector = injector
        self.on_state = on_state
        self.on_test_transcript = on_test_transcript
        self.on_preview = on_preview
        self.on_clear_preview = on_clear_preview
        self.gesture_label = gesture_label
        self.max_recording_seconds = max_recording_seconds
        self.min_recording_seconds = min_recording_seconds
        self.preview_interval_seconds = preview_interval_seconds
        self.state = DictationState.STARTING
        self.last_transcript: str | None = None
        self._recording_started = 0.0
        self._recording_is_test = False
        self._limit_task: asyncio.Task[None] | None = None
        self._preview_task: asyncio.Task[None] | None = None
        self._preview_stop = asyncio.Event()
        self._preview_transcript: str | None = None
        self._operation_lock = asyncio.Lock()

    async def initialise(self) -> None:
        try:
            await self.recogniser.start()
        except Exception as error:
            self._fail(f"Could not start speech recognition: {error}", recover=False)
            raise
        self._set_state(
            DictationState.READY,
            f"Double-tap {self.gesture_label} to dictate",
        )

    @property
    def recording_is_test(self) -> bool:
        return self.state is DictationState.RECORDING and self._recording_is_test

    @property
    def has_preview(self) -> bool:
        return self.state is DictationState.REVIEWING

    @property
    def can_cancel(self) -> bool:
        return self.state in (DictationState.RECORDING, DictationState.REVIEWING)

    async def activate(self, *, test: bool = False) -> None:
        async with self._operation_lock:
            if self.state is not DictationState.READY:
                return
            try:
                await self.capture.start()
            except Exception as error:
                self._fail(f"Could not start the microphone: {error}")
                return
            self._recording_started = monotonic()
            self._recording_is_test = test
            self._preview_transcript = None
            self._preview_stop = asyncio.Event()
            self._set_state(DictationState.RECORDING, "Recording…")
            self._limit_task = asyncio.create_task(self._enforce_limit())
            if not test:
                self._preview_task = asyncio.create_task(self._update_preview())

    async def deactivate(self) -> None:
        async with self._operation_lock:
            if self.state is not DictationState.RECORDING:
                return
            await self._finish_recording()

    async def cancel_recording(self) -> bool:
        async with self._operation_lock:
            if self.state is DictationState.REVIEWING:
                self._clear_preview()
                self._set_state(DictationState.READY, "Preview discarded")
                return True
            if self.state is not DictationState.RECORDING:
                return False
            if self._limit_task:
                self._limit_task.cancel()
                self._limit_task = None
            self._recording_is_test = False
            self._preview_stop.set()
            try:
                await self.capture.cancel()
            except Exception as error:
                self._fail(f"Could not cancel microphone capture: {error}")
                return False
            await self._stop_preview_updates()
            self._set_state(DictationState.READY, "Recording cancelled")
            return True

    async def _finish_recording(self) -> None:
        recording_is_test = self._recording_is_test
        self._recording_is_test = False
        if self._limit_task and self._limit_task is not asyncio.current_task():
            self._limit_task.cancel()
        self._limit_task = None
        duration = monotonic() - self._recording_started
        self._preview_stop.set()
        try:
            pcm = await self.capture.stop()
        except Exception as error:
            self._fail(f"Could not finish microphone capture: {error}")
            return
        await self._stop_preview_updates()
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
            self._clear_preview()
            self._set_state(DictationState.READY, "No speech detected")
            return

        if recording_is_test:
            if self.on_test_transcript:
                self.on_test_transcript(transcript)
            self._set_state(DictationState.READY, "Test transcription ready")
            return

        self._show_preview(transcript)
        self._set_state(
            DictationState.REVIEWING,
            f"Preview ready; double-tap {self.gesture_label} to commit or tap once to discard",
        )

    async def commit_preview(self) -> bool:
        async with self._operation_lock:
            if self.state is not DictationState.REVIEWING or not self._preview_transcript:
                return False
            transcript = self._preview_transcript
            self._clear_preview()
            self._set_state(DictationState.INSERTING, "Committing text…")
            try:
                outcome = await self.injector.insert(transcript)
            except Exception:
                self.last_transcript = transcript
                self._fail("Could not commit text; the full transcript can be copied")
                return False
            self._handle_outcome(transcript, outcome)
            return True

    async def _update_preview(self) -> None:
        while True:
            try:
                await asyncio.wait_for(
                    self._preview_stop.wait(), timeout=self.preview_interval_seconds
                )
                return
            except asyncio.TimeoutError:
                pass
            pcm = self.capture.snapshot()
            if not pcm:
                continue
            try:
                transcript = normalise_transcript(await self.recogniser.transcribe(pcm))
            except Exception as error:
                LOGGER.warning("provisional transcription failed: %s", type(error).__name__)
                continue
            if (
                not self._preview_stop.is_set()
                and self.state is DictationState.RECORDING
                and not self._recording_is_test
            ):
                if transcript:
                    self._show_preview(transcript)

    async def _stop_preview_updates(self) -> None:
        self._preview_stop.set()
        preview_task = self._preview_task
        self._preview_task = None
        if preview_task is not None and preview_task is not asyncio.current_task():
            await preview_task

    def _show_preview(self, transcript: str) -> None:
        if transcript == self._preview_transcript:
            return
        self._preview_transcript = transcript
        if self.on_preview:
            self.on_preview(transcript)

    def _clear_preview(self) -> None:
        self._preview_transcript = None
        if self.on_clear_preview:
            self.on_clear_preview()

    def _handle_outcome(self, transcript: str, outcome: InsertionOutcome) -> None:
        if outcome.status is InsertionStatus.INSERTED:
            self.last_transcript = None
            self._set_state(DictationState.READY, "Text committed")
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
            self._recording_is_test = False
            self._preview_stop.set()
            await self.capture.cancel()
            await self._stop_preview_updates()
        elif self.state is DictationState.REVIEWING:
            self._clear_preview()
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
