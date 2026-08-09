from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from gi.repository import IBus

from speaktext.ibus import (
    IBusTextInjector,
    IBusTextService,
    ModifierTapAction,
    ModifierTapGesture,
)
from speaktext.injector import InsertionStatus
from speaktext.settings import GestureKey


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
        self._speaktext_enabled = False
        self._speaktext_focused = False
        self.values: list[str] = []

    def commit_text(self, text: object) -> None:
        self.values.append(text.get_text())  # type: ignore[attr-defined]


class IBusTextServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = IBusTextService.__new__(IBusTextService)
        self.service.active_engine = None
        self.engine = FakeEngine()

    def test_commits_only_while_engine_is_enabled_and_focused(self) -> None:
        self.engine._speaktext_enabled = True
        self.engine._speaktext_focused = True
        self.service.engine_state_changed(self.engine)  # type: ignore[arg-type]

        self.assertTrue(self.service.commit("hello"))
        self.assertEqual(self.engine.values, ["hello"])

        self.engine._speaktext_focused = False
        self.service.engine_state_changed(self.engine)  # type: ignore[arg-type]
        self.assertFalse(self.service.commit("hidden"))

    def test_dynamic_component_metadata_declares_the_engine(self) -> None:
        component = IBusTextService._component()  # noqa: SLF001
        engines = component.get_engines()

        self.assertEqual(component.get_name(), "local.SpeakText.IBus")
        self.assertEqual(component.get_exec(), "speaktext")
        self.assertEqual([engine.get_name() for engine in engines], ["speaktext"])
        self.assertEqual(engines[0].get_layout(), "default")

    def test_initialisation_activates_the_registered_engine(self) -> None:
        bus = Mock()
        bus.is_connected.return_value = True
        bus.register_component.return_value = True

        with (
            patch("speaktext.ibus.IBus.Bus", return_value=bus),
            patch("speaktext.ibus.SpeakTextEngineFactory"),
        ):
            IBusTextService()

        bus.set_global_engine_async.assert_called_once()
        args = bus.set_global_engine_async.call_args.args
        self.assertEqual(args[:3], ("speaktext", 5_000, None))
        self.assertIs(args[3], IBusTextService._engine_activation_finished)
        self.assertIsNone(args[4])

    def test_failed_engine_activation_is_logged_without_tearing_down(self) -> None:
        bus = Mock()
        bus.set_global_engine_async_finish.return_value = False

        with self.assertLogs("speaktext.ibus", level="ERROR") as logs:
            IBusTextService._engine_activation_finished(bus, Mock(), None)

        self.assertIn("Could not activate", logs.output[0])

    def _prepare_gesture(self, gesture_key: GestureKey) -> list[str]:
        events: list[str] = []
        self.service.gesture_key = gesture_key
        self.service.modifier_gesture = ModifierTapGesture()
        self.service._cancel_source = None  # noqa: SLF001
        self.service.is_recording = lambda: False
        self.service.on_start_or_stop = lambda: events.append("toggle")
        self.service.on_cancel = lambda: events.append("cancel")
        return events

    def test_only_configured_shift_releases_trigger_recording(self) -> None:
        events = self._prepare_gesture(GestureKey.SHIFT)
        release = int(IBus.ModifierType.RELEASE_MASK)

        with patch("speaktext.ibus.monotonic", side_effect=(1.0, 1.2)):
            self.service.process_key_event(IBus.KEY_Shift_L, 0)
            self.service.process_key_event(IBus.KEY_A, release)
            self.service.process_key_event(IBus.KEY_Shift_L, release)
            self.service.process_key_event(IBus.KEY_Shift_R, release)

        self.assertEqual(events, ["toggle"])

    def test_control_can_be_used_for_the_gesture(self) -> None:
        events = self._prepare_gesture(GestureKey.CONTROL)
        release = int(IBus.ModifierType.RELEASE_MASK)

        with patch("speaktext.ibus.monotonic", side_effect=(1.0, 1.2)):
            self.service.process_key_event(IBus.KEY_Shift_L, release)
            self.service.process_key_event(IBus.KEY_Control_L, release)
            self.service.process_key_event(IBus.KEY_Control_R, release)

        self.assertEqual(events, ["toggle"])

    def test_changing_gesture_key_resets_a_pending_tap(self) -> None:
        self._prepare_gesture(GestureKey.SHIFT)
        self.service.modifier_gesture.pending_at = 1.0

        self.service.set_gesture_key(GestureKey.CONTROL)

        self.assertIsNone(self.service.modifier_gesture.pending_at)
        self.assertIs(self.service.gesture_key, GestureKey.CONTROL)

    def test_losing_context_cancels_an_active_recording(self) -> None:
        events: list[str] = []
        self.service.gesture_key = GestureKey.SHIFT
        self.service.modifier_gesture = ModifierTapGesture()
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


class ModifierTapGestureTests(unittest.TestCase):
    def test_double_tap_starts_or_stops_recording(self) -> None:
        gesture = ModifierTapGesture(interval=0.35)

        self.assertIs(gesture.tap(False, 1.0), ModifierTapAction.NONE)
        self.assertIs(
            gesture.tap(False, 1.2), ModifierTapAction.START_OR_STOP
        )

    def test_single_tap_cancels_only_while_recording(self) -> None:
        gesture = ModifierTapGesture(interval=0.35)

        self.assertIs(
            gesture.tap(True, 1.0), ModifierTapAction.SCHEDULE_CANCEL
        )
        self.assertFalse(gesture.expire(True, 1.2))
        self.assertTrue(gesture.expire(True, 1.36))

    def test_slow_taps_do_not_trigger_dictation(self) -> None:
        gesture = ModifierTapGesture(interval=0.35)

        self.assertIs(gesture.tap(False, 1.0), ModifierTapAction.NONE)
        self.assertIs(gesture.tap(False, 1.5), ModifierTapAction.NONE)


if __name__ == "__main__":
    unittest.main()
