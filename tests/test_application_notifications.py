from __future__ import annotations

import unittest
from unittest.mock import Mock

from speaktext.application import SpeakTextApplication, status_notification
from speaktext.coordinator import DictationState


class StatusNotificationTests(unittest.TestCase):
    def test_routine_dictation_states_do_not_notify(self) -> None:
        routine_states = (
            (DictationState.RECORDING, "Recording…"),
            (DictationState.TRANSCRIBING, "Transcribing…"),
            (DictationState.INSERTING, "Inserting text…"),
            (DictationState.READY, "Text inserted"),
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


if __name__ == "__main__":
    unittest.main()
