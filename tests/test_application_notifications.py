from __future__ import annotations

import unittest

from speaktext.application import status_notification
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


if __name__ == "__main__":
    unittest.main()
