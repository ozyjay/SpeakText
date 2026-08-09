from __future__ import annotations

import asyncio
import unittest

from speaktext.coordinator import (
    DictationCoordinator,
    DictationState,
    normalise_transcript,
)
from speaktext.injector import InsertionOutcome, InsertionStatus


class FakeCapture:
    def __init__(self, pcm: bytes = b"\x00\x00" * 8_000) -> None:
        self.pcm = pcm
        self.started = 0
        self.stopped = 0
        self.cancelled = 0

    async def start(self) -> None:
        self.started += 1

    async def stop(self) -> bytes:
        self.stopped += 1
        return self.pcm

    async def cancel(self) -> None:
        self.cancelled += 1


class FakeRecogniser:
    def __init__(self, transcript: str = " hello world ") -> None:
        self.transcript = transcript
        self.started = 0
        self.stopped = 0

    async def start(self) -> None:
        self.started += 1

    async def transcribe(self, _pcm: bytes) -> str:
        return self.transcript

    async def stop(self) -> None:
        self.stopped += 1


class FailingRecogniser(FakeRecogniser):
    async def transcribe(self, _pcm: bytes) -> str:
        raise RuntimeError("recogniser fixture failure")


class FakeInjector:
    def __init__(self, status: InsertionStatus = InsertionStatus.INSERTED) -> None:
        self.status = status
        self.values: list[str] = []

    async def insert(self, text: str) -> InsertionOutcome:
        self.values.append(text)
        return InsertionOutcome(self.status, len(text))


class FailingInjector(FakeInjector):
    async def insert(self, text: str) -> InsertionOutcome:
        self.values.append(text)
        raise RuntimeError("inserter fixture failure")


class CoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.states: list[tuple[DictationState, str]] = []
        self.capture = FakeCapture()
        self.recogniser = FakeRecogniser()
        self.injector = FakeInjector()
        self.coordinator = DictationCoordinator(
            self.capture,
            self.recogniser,
            self.injector,
            lambda state, message: self.states.append((state, message)),
            min_recording_seconds=0,
            max_recording_seconds=10,
        )
        await self.coordinator.initialise()

    async def asyncTearDown(self) -> None:
        await self.coordinator.shutdown()

    async def test_full_dictation_flow(self) -> None:
        await self.coordinator.activate()
        await self.coordinator.activate()
        await self.coordinator.deactivate()

        self.assertEqual(self.capture.started, 1)
        self.assertEqual(self.capture.stopped, 1)
        self.assertEqual(self.injector.values, ["hello world"])
        self.assertEqual(self.coordinator.state, DictationState.READY)
        self.assertIsNone(self.coordinator.last_transcript)

    async def test_clipboard_result_is_recoverable(self) -> None:
        self.injector.status = InsertionStatus.COPIED
        await self.coordinator.activate()
        await self.coordinator.deactivate()
        self.assertEqual(self.coordinator.last_transcript, "hello world")

        self.coordinator.copied_last_transcript()
        self.assertIsNone(self.coordinator.last_transcript)

    async def test_in_window_test_transcribes_without_inserting(self) -> None:
        results: list[str] = []
        self.coordinator.on_test_transcript = results.append

        await self.coordinator.activate(test=True)
        self.assertTrue(self.coordinator.recording_is_test)
        await self.coordinator.deactivate()

        self.assertEqual(results, ["hello world"])
        self.assertEqual(self.injector.values, [])
        self.assertIsNone(self.coordinator.last_transcript)
        self.assertFalse(self.coordinator.recording_is_test)
        self.assertEqual(self.coordinator.state, DictationState.READY)
        self.assertEqual(self.states[-1][1], "Test transcription ready")

    async def test_silence_does_not_inject(self) -> None:
        self.recogniser.transcript = "<|nospeech|> [NO_SPEECH]"
        await self.coordinator.activate()
        await self.coordinator.deactivate()
        self.assertEqual(self.injector.values, [])
        self.assertEqual(self.coordinator.state, DictationState.READY)

    async def test_shutdown_cancels_active_recording(self) -> None:
        await self.coordinator.activate()
        await self.coordinator.shutdown()
        self.assertEqual(self.capture.cancelled, 1)
        self.assertEqual(self.recogniser.stopped, 1)

    async def test_cancel_discards_active_recording(self) -> None:
        await self.coordinator.activate()

        cancelled = await self.coordinator.cancel_recording()

        self.assertTrue(cancelled)
        self.assertEqual(self.capture.cancelled, 1)
        self.assertEqual(self.capture.stopped, 0)
        self.assertEqual(self.injector.values, [])
        self.assertEqual(self.coordinator.state, DictationState.READY)
        self.assertEqual(self.states[-1][1], "Recording cancelled")

    async def test_cancel_is_ignored_when_not_recording(self) -> None:
        self.assertFalse(await self.coordinator.cancel_recording())
        self.assertEqual(self.capture.cancelled, 0)

    async def test_runtime_error_reports_then_recovers_ready_state(self) -> None:
        await self.coordinator.shutdown()
        self.recogniser = FailingRecogniser()
        self.coordinator = DictationCoordinator(
            self.capture,
            self.recogniser,
            self.injector,
            lambda state, message: self.states.append((state, message)),
            min_recording_seconds=0,
        )
        await self.coordinator.initialise()
        await self.coordinator.activate()
        await self.coordinator.deactivate()
        self.assertIn(DictationState.ERROR, [state for state, _ in self.states])
        self.assertEqual(self.coordinator.state, DictationState.READY)

    async def test_insertion_error_keeps_transcript_recoverable(self) -> None:
        self.injector = FailingInjector()
        self.coordinator.injector = self.injector

        await self.coordinator.activate()
        await self.coordinator.deactivate()

        self.assertEqual(self.injector.values, ["hello world"])
        self.assertEqual(self.coordinator.last_transcript, "hello world")
        self.assertIn(DictationState.ERROR, [state for state, _ in self.states])
        self.assertEqual(self.coordinator.state, DictationState.READY)


class TranscriptTests(unittest.TestCase):
    def test_only_outer_whitespace_and_control_tokens_are_removed(self) -> None:
        self.assertEqual(
            normalise_transcript("  Hello,   world. <|endoftext|>  "),
            "Hello,   world.",
        )


if __name__ == "__main__":
    unittest.main()
