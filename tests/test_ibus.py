from __future__ import annotations

import unittest
from unittest.mock import patch

from gi.repository import IBus

from speaktext.ibus import (
    IBusTextInjector,
    IBusTextService,
    ShiftTapAction,
    ShiftTapGesture,
)
from speaktext.injector import InsertionStatus


class FakeCommitter:
    def __init__(self, available: bool) -> None:
        self.available = available
        self.values: list[str] = []

    def commit(self, text: str) -> bool:
        self.values.append(text)
        return self.available


class FakeClipboard:
    def __init__(self) -> None:
        self.values: list[str] = []

    def copy(self, text: str) -> None:
        self.values.append(text)


class FakeEngine:
    def __init__(self) -> None:
        self.enabled = False
        self.focused = False
        self.values: list[str] = []

    def commit_text(self, text: object) -> None:
        self.values.append(text.get_text())  # type: ignore[attr-defined]


class IBusTextServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = IBusTextService.__new__(IBusTextService)
        self.service.active_engine = None
        self.engine = FakeEngine()

    def test_commits_only_while_engine_is_enabled_and_focused(self) -> None:
        self.engine.enabled = True
        self.engine.focused = True
        self.service.engine_state_changed(self.engine)  # type: ignore[arg-type]

        self.assertTrue(self.service.commit("hello"))
        self.assertEqual(self.engine.values, ["hello"])

        self.engine.focused = False
        self.service.engine_state_changed(self.engine)  # type: ignore[arg-type]
        self.assertFalse(self.service.commit("hidden"))

    def test_dynamic_component_metadata_declares_the_engine(self) -> None:
        component = IBusTextService._component()  # noqa: SLF001
        engines = component.get_engines()

        self.assertEqual(component.get_name(), "local.SpeakText.IBus")
        self.assertEqual(component.get_exec(), "speaktext")
        self.assertEqual([engine.get_name() for engine in engines], ["speaktext"])
        self.assertEqual(engines[0].get_layout(), "default")

    def test_only_rapid_shift_releases_trigger_recording(self) -> None:
        events: list[str] = []
        self.service.shift_gesture = ShiftTapGesture()
        self.service._cancel_source = None  # noqa: SLF001
        self.service.is_recording = lambda: False
        self.service.on_start_or_stop = lambda: events.append("toggle")
        self.service.on_cancel = lambda: events.append("cancel")
        release = int(IBus.ModifierType.RELEASE_MASK)

        with patch("speaktext.ibus.monotonic", side_effect=(1.0, 1.2)):
            self.service.process_key_event(IBus.KEY_Shift_L, 0)
            self.service.process_key_event(IBus.KEY_A, release)
            self.service.process_key_event(IBus.KEY_Shift_L, release)
            self.service.process_key_event(IBus.KEY_Shift_R, release)

        self.assertEqual(events, ["toggle"])

    def test_losing_context_cancels_an_active_recording(self) -> None:
        events: list[str] = []
        self.service.shift_gesture = ShiftTapGesture()
        self.service._cancel_source = None  # noqa: SLF001
        self.service.is_recording = lambda: True
        self.service.on_cancel = lambda: events.append("cancel")

        self.service.context_lost()

        self.assertEqual(events, ["cancel"])


class IBusTextInjectorTests(unittest.IsolatedAsyncioTestCase):
    async def test_commits_to_active_input_context(self) -> None:
        committer = FakeCommitter(True)
        clipboard = FakeClipboard()

        outcome = await IBusTextInjector(committer, clipboard).insert("hello")

        self.assertEqual(outcome.status, InsertionStatus.INSERTED)
        self.assertEqual(outcome.sent_characters, 5)
        self.assertEqual(committer.values, ["hello"])
        self.assertEqual(clipboard.values, [])

    async def test_copies_when_input_method_is_not_active(self) -> None:
        committer = FakeCommitter(False)
        clipboard = FakeClipboard()

        outcome = await IBusTextInjector(committer, clipboard).insert("hello")

        self.assertEqual(outcome.status, InsertionStatus.COPIED)
        self.assertEqual(clipboard.values, ["hello"])


class ShiftTapGestureTests(unittest.TestCase):
    def test_double_tap_starts_or_stops_recording(self) -> None:
        gesture = ShiftTapGesture(interval=0.35)

        self.assertIs(gesture.tap(False, 1.0), ShiftTapAction.NONE)
        self.assertIs(
            gesture.tap(False, 1.2), ShiftTapAction.START_OR_STOP
        )

    def test_single_tap_cancels_only_while_recording(self) -> None:
        gesture = ShiftTapGesture(interval=0.35)

        self.assertIs(
            gesture.tap(True, 1.0), ShiftTapAction.SCHEDULE_CANCEL
        )
        self.assertFalse(gesture.expire(True, 1.2))
        self.assertTrue(gesture.expire(True, 1.36))

    def test_slow_taps_do_not_trigger_dictation(self) -> None:
        gesture = ShiftTapGesture(interval=0.35)

        self.assertIs(gesture.tap(False, 1.0), ShiftTapAction.NONE)
        self.assertIs(gesture.tap(False, 1.5), ShiftTapAction.NONE)


if __name__ == "__main__":
    unittest.main()
