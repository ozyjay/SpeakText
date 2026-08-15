from __future__ import annotations

import unittest
from unittest.mock import Mock

from speaktext.application import SpeakTextApplication, status_notification
from speaktext.coordinator import DictationState
from speaktext.settings import GestureKey


class StatusNotificationTests(unittest.TestCase):
    def test_routine_dictation_states_do_not_notify(self) -> None:
        routine_states = (
            (DictationState.RECORDING, "Recording…"),
            (DictationState.TRANSCRIBING, "Transcribing…"),
            (DictationState.REVIEWING, "Preview ready"),
            (DictationState.INSERTING, "Inserting text…"),
            (DictationState.READY, "Text committed"),
        )

        for state, message in routine_states:
            with self.subTest(state=state):
                self.assertIsNone(status_notification(state, message))

    def test_errors_notify(self) -> None:
        self.assertEqual(
            status_notification(DictationState.ERROR, "Portal unavailable"),
            ("dictation-error", "SpeakText error", "Portal unavailable"),
        )

    def test_clipboard_fallback_notifies(self) -> None:
        message = "Text copied; paste it at the cursor"

        self.assertEqual(
            status_notification(DictationState.READY, message),
            ("dictation-result", "SpeakText", message),
        )


class StartupProgressTests(unittest.TestCase):
    def test_progress_is_retained_before_the_window_exists(self) -> None:
        application = SpeakTextApplication.__new__(SpeakTextApplication)
        application.progress = None
        application._startup_progress_text = "Checking model"
        application._startup_progress_fraction = 0.0

        application._set_startup_progress("Loading local speech recognition…")

        self.assertEqual(
            application._startup_progress_text, "Loading local speech recognition…"
        )
        self.assertIsNone(application._startup_progress_fraction)

    def test_queued_download_progress_does_not_replace_loading_status(self) -> None:
        application = SpeakTextApplication.__new__(SpeakTextApplication)
        application._model_download_complete = True
        application._model_download_started = False
        application._stop_progress_pulse = Mock()
        application._set_status = Mock()
        application._set_startup_progress = Mock()

        application._model_progress(1024, 2048)

        application._stop_progress_pulse.assert_not_called()
        application._set_status.assert_not_called()
        application._set_startup_progress.assert_not_called()


class TestDictationControlsTests(unittest.TestCase):
    def test_reactivate_input_source_requests_ibus_engine_activation(self) -> None:
        application = SpeakTextApplication.__new__(SpeakTextApplication)
        application.ibus_service = Mock()
        application.reactivate_input_button = Mock()

        application._reactivate_input_source()

        application.reactivate_input_button.set_sensitive.assert_called_once_with(False)
        application.ibus_service.activate_engine.assert_called_once_with(
            application._input_source_reactivated
        )

    def test_reactivated_input_source_updates_ready_status(self) -> None:
        application = SpeakTextApplication.__new__(SpeakTextApplication)
        application.reactivate_input_button = Mock()
        application.gesture_key = GestureKey.CONTROL
        application._set_status = Mock()

        application._input_source_reactivated(True)

        application.reactivate_input_button.set_sensitive.assert_called_once_with(True)
        application._set_status.assert_called_once_with(
            DictationState.READY,
            "SpeakText input source reactivated; double-tap Control to dictate",
        )

    def test_stop_test_remains_available_while_a_test_is_recording(self) -> None:
        application = SpeakTextApplication.__new__(SpeakTextApplication)
        application.coordinator = Mock(
            last_transcript=None,
            recording_is_test=True,
        )
        application.status_row = None
        application.status_label = None
        application.cancel_button = None
        application.gesture_key_row = None
        application.copy_button = None
        application.test_button = Mock()
        application.control_service = None
        application.withdraw_notification = Mock()
        application._notify = Mock()

        application._set_status(DictationState.RECORDING, "Recording…")

        application.test_button.set_sensitive.assert_called_once_with(True)
        application.test_button.set_label.assert_called_once_with("Stop test")


if __name__ == "__main__":
    unittest.main()
