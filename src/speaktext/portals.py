from __future__ import annotations

import asyncio
import logging
import secrets
from collections.abc import Callable
from typing import Any

from gi.repository import Gio, GLib

from .constants import APP_ID, SHORTCUT_ID, SHORTCUT_TRIGGER

LOGGER = logging.getLogger(__name__)
PORTAL_NAME = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
REQUEST_INTERFACE = "org.freedesktop.portal.Request"
HOST_REGISTRY_INTERFACE = "org.freedesktop.host.portal.Registry"
GLOBAL_SHORTCUTS_INTERFACE = "org.freedesktop.portal.GlobalShortcuts"
REMOTE_DESKTOP_INTERFACE = "org.freedesktop.portal.RemoteDesktop"
KEYBOARD_DEVICE = 1

PortalResult = dict[str, Any]
SuccessCallback = Callable[[PortalResult], None]
ErrorCallback = Callable[[Exception], None]


class PortalError(RuntimeError):
    pass


def _value(value: Any) -> Any:
    return value.unpack() if isinstance(value, GLib.Variant) else value


class PortalRequestRunner:
    """Run asynchronous portal requests without racing the Response signal."""

    def __init__(self, connection: Gio.DBusConnection | None = None) -> None:
        self.connection = connection or Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self._register_host_app()

    def _register_host_app(self) -> None:
        try:
            self.connection.call_sync(
                PORTAL_NAME,
                PORTAL_PATH,
                HOST_REGISTRY_INTERFACE,
                "Register",
                GLib.Variant("(sa{sv})", (APP_ID, {})),
                None,
                Gio.DBusCallFlags.NONE,
                2_000,
                None,
            )
        except GLib.Error as error:
            # Older portal versions may not provide the host registry. They can
            # still identify conventionally launched applications themselves.
            LOGGER.warning("host portal app registration unavailable: %s", error.message)

    def token(self, prefix: str) -> str:
        return f"{prefix}_{secrets.token_hex(8)}"

    def request_path(self, token: str) -> str:
        unique_name = self.connection.get_unique_name() or ":0.0"
        sender = unique_name.removeprefix(":").replace(".", "_")
        return f"{PORTAL_PATH}/request/{sender}/{token}"

    def request(
        self,
        interface: str,
        method: str,
        parameters: GLib.Variant,
        token: str,
        on_success: SuccessCallback,
        on_error: ErrorCallback,
    ) -> None:
        path = self.request_path(token)
        completed = False

        def fail(error: Exception) -> None:
            nonlocal completed
            if completed:
                return
            completed = True
            self.connection.signal_unsubscribe(subscription)
            on_error(error)

        def response_received(
            _connection: Gio.DBusConnection,
            _sender: str,
            _path: str,
            _interface: str,
            _signal: str,
            response_parameters: GLib.Variant,
            _user_data: Any,
        ) -> None:
            nonlocal completed
            if completed:
                return
            completed = True
            self.connection.signal_unsubscribe(subscription)
            response, results = response_parameters.unpack()
            if response != 0:
                on_error(PortalError(f"Portal request {method} was denied ({response})"))
                return
            on_success({key: _value(value) for key, value in results.items()})

        subscription = self.connection.signal_subscribe(
            PORTAL_NAME,
            REQUEST_INTERFACE,
            "Response",
            path,
            None,
            Gio.DBusSignalFlags.NONE,
            response_received,
            None,
        )

        def call_finished(
            connection: Gio.DBusConnection,
            result: Gio.AsyncResult,
            _user_data: Any,
        ) -> None:
            try:
                connection.call_finish(result)
            except GLib.Error as error:
                fail(PortalError(f"Portal method {method} failed: {error.message}"))

        self.connection.call(
            PORTAL_NAME,
            PORTAL_PATH,
            interface,
            method,
            parameters,
            GLib.VariantType.new("(o)"),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            call_finished,
            None,
        )


class GlobalShortcutPortal:
    def __init__(self, runner: PortalRequestRunner | None = None) -> None:
        self.runner = runner or PortalRequestRunner()
        self.session_handle: str | None = None
        self._signal_subscription: int | None = None
        self._activated: Callable[[], None] | None = None
        self._deactivated: Callable[[], None] | None = None

    def initialise(
        self,
        activated: Callable[[], None],
        deactivated: Callable[[], None],
        on_ready: Callable[[str], None],
        on_error: ErrorCallback,
    ) -> None:
        self._activated = activated
        self._deactivated = deactivated
        token = self.runner.token("shortcut_create")
        options = {
            "handle_token": GLib.Variant("s", token),
            "session_handle_token": GLib.Variant(
                "s", self.runner.token("shortcut_session")
            ),
        }
        self.runner.request(
            GLOBAL_SHORTCUTS_INTERFACE,
            "CreateSession",
            GLib.Variant("(a{sv})", (options,)),
            token,
            lambda result: self._bind(result, on_ready, on_error),
            on_error,
        )

    def _bind(
        self,
        result: PortalResult,
        on_ready: Callable[[str], None],
        on_error: ErrorCallback,
    ) -> None:
        session = result.get("session_handle")
        if not isinstance(session, str):
            on_error(PortalError("Shortcut portal returned no session"))
            return
        self.session_handle = session
        self._subscribe_signals()

        token = self.runner.token("shortcut_bind")
        options = {"handle_token": GLib.Variant("s", token)}
        shortcuts = [
            (
                SHORTCUT_ID,
                {
                    "description": GLib.Variant("s", "Hold to dictate"),
                    "preferred_trigger": GLib.Variant("s", SHORTCUT_TRIGGER),
                },
            )
        ]
        parameters = GLib.Variant(
            "(oa(sa{sv})sa{sv})", (session, shortcuts, "", options)
        )
        self.runner.request(
            GLOBAL_SHORTCUTS_INTERFACE,
            "BindShortcuts",
            parameters,
            token,
            lambda bind_result: self._bound(bind_result, on_ready, on_error),
            on_error,
        )

    @staticmethod
    def _bound(
        result: PortalResult,
        on_ready: Callable[[str], None],
        on_error: ErrorCallback,
    ) -> None:
        shortcuts = result.get("shortcuts", [])
        for shortcut_id, properties in shortcuts:
            if shortcut_id == SHORTCUT_ID:
                trigger = _value(properties.get("trigger_description", SHORTCUT_TRIGGER))
                on_ready(str(trigger))
                return
        on_error(PortalError("No dictation shortcut was bound"))

    def _subscribe_signals(self) -> None:
        if self._signal_subscription is not None:
            return

        def signal_received(
            _connection: Gio.DBusConnection,
            _sender: str,
            _path: str,
            _interface: str,
            signal: str,
            parameters: GLib.Variant,
            _user_data: Any,
        ) -> None:
            self._handle_shortcut_signal(signal, parameters)

        self._signal_subscription = self.runner.connection.signal_subscribe(
            PORTAL_NAME,
            GLOBAL_SHORTCUTS_INTERFACE,
            None,
            PORTAL_PATH,
            None,
            Gio.DBusSignalFlags.NONE,
            signal_received,
            None,
        )

    def _handle_shortcut_signal(
        self, signal: str, parameters: GLib.Variant
    ) -> None:
        if signal not in {"Activated", "Deactivated"}:
            return

        values = parameters.unpack()
        if not isinstance(values, tuple) or len(values) != 4:
            LOGGER.warning("ignored malformed global shortcut signal=%s", signal)
            return

        session, shortcut_id, _timestamp, _options = values
        if session != self.session_handle or shortcut_id != SHORTCUT_ID:
            return
        if signal == "Activated" and self._activated:
            self._activated()
        elif signal == "Deactivated" and self._deactivated:
            self._deactivated()

    def close(self) -> None:
        if self._signal_subscription is not None:
            self.runner.connection.signal_unsubscribe(self._signal_subscription)
            self._signal_subscription = None
        if self.session_handle:
            self.runner.connection.call(
                PORTAL_NAME,
                self.session_handle,
                "org.freedesktop.portal.Session",
                "Close",
                None,
                None,
                Gio.DBusCallFlags.NONE,
                -1,
                None,
                None,
                None,
            )
            self.session_handle = None


class KeyboardPortal:
    def __init__(self, runner: PortalRequestRunner | None = None) -> None:
        self.runner = runner or PortalRequestRunner()
        self.session_handle: str | None = None

    @property
    def ready(self) -> bool:
        return self.session_handle is not None

    async def open(self, restore_token: str | None) -> str | None:
        if self.session_handle is not None:
            raise PortalError("Keyboard portal session is already open")

        future: asyncio.Future[str | None] = (
            asyncio.get_running_loop().create_future()
        )

        def ready(refreshed_token: str | None) -> None:
            if future.done():
                self.close()
                return
            future.set_result(refreshed_token)

        def failed(error: Exception) -> None:
            self.close()
            if not future.done():
                future.set_exception(error)

        self._create_session(restore_token, ready, failed)
        try:
            return await future
        except asyncio.CancelledError:
            self.close()
            raise

    def _create_session(
        self,
        restore_token: str | None,
        on_ready: Callable[[str | None], None],
        on_error: ErrorCallback,
    ) -> None:
        token = self.runner.token("remote_create")
        options = {
            "handle_token": GLib.Variant("s", token),
            "session_handle_token": GLib.Variant(
                "s", self.runner.token("remote_session")
            ),
        }
        self.runner.request(
            REMOTE_DESKTOP_INTERFACE,
            "CreateSession",
            GLib.Variant("(a{sv})", (options,)),
            token,
            lambda result: self._select_devices(
                result, restore_token, on_ready, on_error
            ),
            on_error,
        )

    def _select_devices(
        self,
        result: PortalResult,
        restore_token: str | None,
        on_ready: Callable[[str | None], None],
        on_error: ErrorCallback,
    ) -> None:
        session = result.get("session_handle")
        if not isinstance(session, str):
            on_error(PortalError("Keyboard portal returned no session"))
            return
        self.session_handle = session
        token = self.runner.token("remote_select")
        options: dict[str, GLib.Variant] = {
            "handle_token": GLib.Variant("s", token),
            "types": GLib.Variant("u", KEYBOARD_DEVICE),
            "persist_mode": GLib.Variant("u", 2),
        }
        if restore_token:
            options["restore_token"] = GLib.Variant("s", restore_token)
        self.runner.request(
            REMOTE_DESKTOP_INTERFACE,
            "SelectDevices",
            GLib.Variant("(oa{sv})", (session, options)),
            token,
            lambda _result: self._start(on_ready, on_error),
            on_error,
        )

    def _start(
        self,
        on_ready: Callable[[str | None], None],
        on_error: ErrorCallback,
    ) -> None:
        assert self.session_handle is not None
        token = self.runner.token("remote_start")
        options = {"handle_token": GLib.Variant("s", token)}
        self.runner.request(
            REMOTE_DESKTOP_INTERFACE,
            "Start",
            GLib.Variant("(osa{sv})", (self.session_handle, "", options)),
            token,
            lambda result: self._started(result, on_ready, on_error),
            on_error,
        )

    @staticmethod
    def _started(
        result: PortalResult,
        on_ready: Callable[[str | None], None],
        on_error: ErrorCallback,
    ) -> None:
        devices = int(result.get("devices", 0))
        if not devices & KEYBOARD_DEVICE:
            on_error(PortalError("Keyboard control was not granted"))
            return
        token = result.get("restore_token")
        on_ready(token if isinstance(token, str) else None)

    def send_keysym(self, keysym: int, pressed: bool) -> None:
        if self.session_handle is None:
            raise PortalError("Keyboard portal is not ready")
        parameters = GLib.Variant(
            "(oa{sv}iu)",
            (self.session_handle, {}, keysym, 1 if pressed else 0),
        )
        try:
            self.runner.connection.call_sync(
                PORTAL_NAME,
                PORTAL_PATH,
                REMOTE_DESKTOP_INTERFACE,
                "NotifyKeyboardKeysym",
                parameters,
                None,
                Gio.DBusCallFlags.NONE,
                2_000,
                None,
            )
        except GLib.Error as error:
            raise PortalError(f"Keyboard injection failed: {error.message}") from error

    def close(self) -> None:
        if self.session_handle:
            self.runner.connection.call(
                PORTAL_NAME,
                self.session_handle,
                "org.freedesktop.portal.Session",
                "Close",
                None,
                None,
                Gio.DBusCallFlags.NONE,
                -1,
                None,
                None,
                None,
            )
            self.session_handle = None
