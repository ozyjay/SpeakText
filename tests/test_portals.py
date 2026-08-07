from __future__ import annotations

import unittest
from unittest.mock import patch

from gi.repository import Gio, GLib

from speaktext.constants import (
    APP_ID,
    CANCEL_SHORTCUT_ID,
    CANCEL_SHORTCUT_TRIGGER,
    SHORTCUT_ID,
    SHORTCUT_TRIGGER,
)
from speaktext.portals import (
    GlobalShortcutPortal,
    HOST_REGISTRY_INTERFACE,
    KEYBOARD_DEVICE,
    KeyboardPortal,
    PORTAL_NAME,
    PORTAL_PATH,
    PortalError,
    PortalRequestRunner,
)


class FakeParameters:
    def __init__(self, values: tuple[object, ...]) -> None:
        self.values = values

    def unpack(self) -> tuple[object, ...]:
        return self.values


class UnexpectedParameters:
    def unpack(self) -> tuple[object, ...]:
        raise AssertionError("unrelated signals must not be unpacked")


class FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def get_unique_name(self) -> str:
        return ":1.245"

    def call_sync(self, *args: object) -> None:
        self.calls.append(args)

    def call(self, *args: object) -> None:
        self.calls.append(args)


class UnavailableRegistryConnection(FakeConnection):
    def call_sync(self, *args: object) -> None:
        raise GLib.Error.new_literal(
            Gio.dbus_error_quark(),
            "registry unavailable",
            Gio.DBusError.UNKNOWN_METHOD,
        )


class RejectedRegistryConnection(FakeConnection):
    def call_sync(self, *args: object) -> None:
        raise GLib.Error("connection already associated")


class ShortcutConnection(FakeConnection):
    def signal_subscribe(self, *args: object) -> int:
        self.calls.append(args)
        return 1


class CapturingShortcutRunner:
    def __init__(self) -> None:
        self.connection = ShortcutConnection()
        self.requests: list[tuple[str, object]] = []

    @staticmethod
    def token(prefix: str) -> str:
        return f"{prefix}_token"

    def request(
        self,
        _interface: str,
        method: str,
        parameters: object,
        _token: str,
        _on_success: object,
        _on_error: object,
    ) -> None:
        self.requests.append((method, parameters))


class ImmediateKeyboardRunner:
    def __init__(self, fail_method: str | None = None) -> None:
        self.connection = FakeConnection()
        self.fail_method = fail_method
        self.requests: list[tuple[str, object]] = []
        self._token_number = 0

    def token(self, prefix: str) -> str:
        self._token_number += 1
        return f"{prefix}_{self._token_number}"

    def request(
        self,
        _interface: str,
        method: str,
        parameters: object,
        _token: str,
        on_success: object,
        on_error: object,
    ) -> None:
        self.requests.append((method, parameters))
        if method == self.fail_method:
            on_error(PortalError(f"{method} denied"))  # type: ignore[operator]
        elif method == "CreateSession":
            on_success(  # type: ignore[operator]
                {"session_handle": "/org/freedesktop/portal/session/test"}
            )
        elif method == "SelectDevices":
            on_success({})  # type: ignore[operator]
        elif method == "Start":
            on_success(  # type: ignore[operator]
                {"devices": KEYBOARD_DEVICE, "restore_token": "new-token"}
            )


class PortalTests(unittest.TestCase):
    def test_uses_dedicated_connection_by_default(self) -> None:
        connection = FakeConnection()

        with patch(
            "speaktext.portals._new_session_bus_connection",
            return_value=connection,
        ) as new_connection:
            runner = PortalRequestRunner()

        new_connection.assert_called_once_with()
        self.assertIs(runner.connection, connection)
        self.assertEqual(connection.calls[0][3], "Register")

    def test_request_path_uses_dbus_unique_name(self) -> None:
        runner = PortalRequestRunner(FakeConnection())  # type: ignore[arg-type]
        self.assertEqual(
            runner.request_path("token"),
            "/org/freedesktop/portal/desktop/request/1_245/token",
        )

    def test_registers_app_id_before_portal_requests(self) -> None:
        connection = FakeConnection()

        PortalRequestRunner(connection)  # type: ignore[arg-type]

        self.assertEqual(len(connection.calls), 1)
        call = connection.calls[0]
        self.assertEqual(
            call[:4],
            (PORTAL_NAME, PORTAL_PATH, HOST_REGISTRY_INTERFACE, "Register"),
        )
        self.assertEqual(call[4].unpack(), (APP_ID, {}))  # type: ignore[union-attr]

    def test_missing_host_registry_falls_back_to_portal_detection(self) -> None:
        with self.assertLogs("speaktext.portals", level="WARNING") as logs:
            PortalRequestRunner(  # type: ignore[arg-type]
                UnavailableRegistryConnection()
            )

        self.assertIn("host portal app registration unavailable", logs.output[0])

    def test_registration_failure_is_not_silently_ignored(self) -> None:
        with self.assertRaisesRegex(
            PortalError, "Could not register desktop portal app ID"
        ):
            PortalRequestRunner(  # type: ignore[arg-type]
                RejectedRegistryConnection()
            )

    def test_ignores_shortcuts_changed_signal_before_unpacking(self) -> None:
        portal = GlobalShortcutPortal(object())  # type: ignore[arg-type]

        portal._handle_shortcut_signal(  # noqa: SLF001
            "ShortcutsChanged",
            UnexpectedParameters(),  # type: ignore[arg-type]
        )

    def test_dispatches_activated_and_deactivated_signals(self) -> None:
        portal = GlobalShortcutPortal(object())  # type: ignore[arg-type]
        portal.session_handle = "/org/freedesktop/portal/desktop/session/test"
        events: list[str] = []
        portal._activated = lambda: events.append("activated")  # noqa: SLF001
        portal._deactivated = lambda: events.append("deactivated")  # noqa: SLF001
        parameters = FakeParameters(
            (portal.session_handle, "dictate", 123, {})
        )

        portal._handle_shortcut_signal(  # type: ignore[arg-type]  # noqa: SLF001
            "Activated", parameters
        )
        portal._handle_shortcut_signal(  # type: ignore[arg-type]  # noqa: SLF001
            "Deactivated", parameters
        )

        self.assertEqual(events, ["activated", "deactivated"])

    def test_binds_dictation_and_cancel_shortcuts(self) -> None:
        runner = CapturingShortcutRunner()
        portal = GlobalShortcutPortal(runner)  # type: ignore[arg-type]

        portal._bind(  # noqa: SLF001
            {"session_handle": "/org/freedesktop/portal/session/test"},
            lambda _dictate, _cancel: None,
            self.fail,
        )

        self.assertEqual(runner.requests[0][0], "BindShortcuts")
        parameters = runner.requests[0][1]
        values = parameters.unpack()  # type: ignore[union-attr]
        _session, shortcuts, _parent, _options = values
        properties = dict(shortcuts)
        self.assertEqual(properties[SHORTCUT_ID]["preferred_trigger"], SHORTCUT_TRIGGER)
        self.assertEqual(
            properties[CANCEL_SHORTCUT_ID]["preferred_trigger"],
            CANCEL_SHORTCUT_TRIGGER,
        )

    def test_dispatches_cancel_activation_only(self) -> None:
        portal = GlobalShortcutPortal(object())  # type: ignore[arg-type]
        portal.session_handle = "/org/freedesktop/portal/desktop/session/test"
        events: list[str] = []
        portal._cancelled = lambda: events.append("cancelled")  # noqa: SLF001
        parameters = FakeParameters(
            (portal.session_handle, CANCEL_SHORTCUT_ID, 123, {})
        )

        portal._handle_shortcut_signal(  # type: ignore[arg-type]  # noqa: SLF001
            "Activated", parameters
        )
        portal._handle_shortcut_signal(  # type: ignore[arg-type]  # noqa: SLF001
            "Deactivated", parameters
        )

        self.assertEqual(events, ["cancelled"])

    def test_reports_both_bound_shortcuts(self) -> None:
        ready: list[tuple[str, str]] = []
        errors: list[Exception] = []
        result = {
            "shortcuts": [
                (
                    SHORTCUT_ID,
                    {"trigger_description": GLib.Variant("s", "Ctrl+Alt+Space")},
                ),
                (
                    CANCEL_SHORTCUT_ID,
                    {"trigger_description": GLib.Variant("s", "Ctrl+Alt+Esc")},
                ),
            ]
        }

        GlobalShortcutPortal._bound(  # noqa: SLF001
            result,
            lambda dictate, cancel: ready.append((dictate, cancel)),
            errors.append,
        )

        self.assertEqual(ready, [("Ctrl+Alt+Space", "Ctrl+Alt+Esc")])
        self.assertEqual(errors, [])

    def test_missing_cancel_shortcut_keeps_dictation_available(self) -> None:
        ready: list[tuple[str, str]] = []
        errors: list[Exception] = []

        GlobalShortcutPortal._bound(  # noqa: SLF001
            {"shortcuts": [(SHORTCUT_ID, {})]},
            lambda dictate, cancel: ready.append((dictate, cancel)),
            errors.append,
        )

        self.assertEqual(ready, [(SHORTCUT_TRIGGER, "Not bound")])
        self.assertEqual(errors, [])

    def test_missing_dictation_shortcut_is_an_error(self) -> None:
        errors: list[Exception] = []

        GlobalShortcutPortal._bound(  # noqa: SLF001
            {"shortcuts": [(CANCEL_SHORTCUT_ID, {})]},
            lambda _dictate, _cancel: self.fail("dictation must be bound"),
            errors.append,
        )

        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], PortalError)
        self.assertIn("No dictation shortcut", str(errors[0]))

    def test_malformed_activation_signal_is_ignored(self) -> None:
        portal = GlobalShortcutPortal(object())  # type: ignore[arg-type]

        with self.assertLogs("speaktext.portals", level="WARNING") as logs:
            portal._handle_shortcut_signal(  # type: ignore[arg-type]  # noqa: SLF001
                "Activated", FakeParameters(("session", "dictate"))
            )

        self.assertIn("ignored malformed global shortcut signal", logs.output[0])


class KeyboardPortalTests(unittest.IsolatedAsyncioTestCase):
    async def test_opens_with_restore_token_and_closes_on_demand(self) -> None:
        runner = ImmediateKeyboardRunner()
        portal = KeyboardPortal(runner)  # type: ignore[arg-type]

        token = await portal.open("old-token")

        self.assertEqual(token, "new-token")
        self.assertTrue(portal.ready)
        methods = [method for method, _parameters in runner.requests]
        self.assertEqual(methods, ["CreateSession", "SelectDevices", "Start"])
        select_parameters = runner.requests[1][1]
        _session, options = select_parameters.unpack()  # type: ignore[union-attr]
        self.assertEqual(options["types"], KEYBOARD_DEVICE)
        self.assertEqual(options["persist_mode"], 2)
        self.assertEqual(options["restore_token"], "old-token")

        portal.close()

        self.assertFalse(portal.ready)
        self.assertEqual(runner.connection.calls[-1][3], "Close")

    async def test_failed_open_closes_created_session(self) -> None:
        runner = ImmediateKeyboardRunner(fail_method="SelectDevices")
        portal = KeyboardPortal(runner)  # type: ignore[arg-type]

        with self.assertRaisesRegex(PortalError, "SelectDevices denied"):
            await portal.open("old-token")

        self.assertFalse(portal.ready)
        self.assertEqual(runner.connection.calls[-1][3], "Close")


if __name__ == "__main__":
    unittest.main()
