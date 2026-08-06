from __future__ import annotations

import unittest

from speaktext.control import CONTROL_INTERFACE, CONTROL_PATH, ControlService


class FakeConnection:
    def __init__(self) -> None:
        self.callback = None
        self.signals: list[tuple[object, ...]] = []
        self.unregistered: list[int] = []

    def register_object(
        self,
        path: str,
        interface: object,
        callback: object,
        _get_property: object,
        _set_property: object,
    ) -> int:
        self.path = path
        self.interface = interface
        self.callback = callback
        return 42

    def emit_signal(self, *args: object) -> bool:
        self.signals.append(args)
        return True

    def unregister_object(self, registration_id: int) -> bool:
        self.unregistered.append(registration_id)
        return True


class FakeInvocation:
    def __init__(self) -> None:
        self.value = None
        self.error = None

    def return_value(self, value: object) -> None:
        self.value = value

    def return_dbus_error(self, name: str, message: str) -> None:
        self.error = (name, message)


class ControlServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = FakeConnection()
        self.activated = 0
        self.copied = 0
        self.quit = 0
        self.service = ControlService(
            self.connection,  # type: ignore[arg-type]
            lambda: setattr(self, "activated", self.activated + 1),
            self._copy,
            lambda: setattr(self, "quit", self.quit + 1),
        )

    def _copy(self) -> bool:
        self.copied += 1
        return True

    def call(self, method: str) -> FakeInvocation:
        invocation = FakeInvocation()
        self.service._on_method_call(  # noqa: SLF001
            self.connection,  # type: ignore[arg-type]
            "sender",
            CONTROL_PATH,
            CONTROL_INTERFACE,
            method,
            None,  # type: ignore[arg-type]
            invocation,  # type: ignore[arg-type]
        )
        return invocation

    def test_status_update_emits_content_free_signal(self) -> None:
        self.service.update("Recording", "Recording…", False)
        self.assertEqual(len(self.connection.signals), 1)
        signal = self.connection.signals[0]
        self.assertEqual(signal[1:4], (CONTROL_PATH, CONTROL_INTERFACE, "StatusChanged"))
        self.assertEqual(signal[4].unpack(), ("Recording", "Recording…", False))

    def test_get_status_and_copy_action(self) -> None:
        self.service.update("Error", "Insertion incomplete", True)
        self.assertEqual(
            self.call("GetStatus").value.unpack(),
            ("Error", "Insertion incomplete", True),
        )
        self.assertEqual(self.call("CopyLastTranscript").value.unpack(), (True,))
        self.assertEqual(self.copied, 1)

    def test_close_unregisters_object(self) -> None:
        self.service.close()
        self.assertEqual(self.connection.unregistered, [42])


if __name__ == "__main__":
    unittest.main()

