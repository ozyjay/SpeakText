from __future__ import annotations

from collections.abc import Callable

from gi.repository import Gio, GLib

CONTROL_PATH = "/local/SpeakText"
CONTROL_INTERFACE = "local.SpeakText.Control"

CONTROL_XML = f"""
<node>
  <interface name="{CONTROL_INTERFACE}">
    <method name="GetStatus">
      <arg name="state" type="s" direction="out"/>
      <arg name="message" type="s" direction="out"/>
      <arg name="can_copy" type="b" direction="out"/>
    </method>
    <method name="ActivateWindow"/>
    <method name="CopyLastTranscript">
      <arg name="copied" type="b" direction="out"/>
    </method>
    <method name="CancelRecording"/>
    <method name="Quit"/>
    <signal name="StatusChanged">
      <arg name="state" type="s"/>
      <arg name="message" type="s"/>
      <arg name="can_copy" type="b"/>
    </signal>
  </interface>
</node>
"""


class ControlService:
    """Expose non-sensitive application state and top-bar actions over D-Bus."""

    def __init__(
        self,
        connection: Gio.DBusConnection,
        activate_window: Callable[[], None],
        copy_last_transcript: Callable[[], bool],
        cancel_recording: Callable[[], None],
        quit_application: Callable[[], None],
    ) -> None:
        self.connection = connection
        self.activate_window = activate_window
        self.copy_last_transcript = copy_last_transcript
        self.cancel_recording = cancel_recording
        self.quit_application = quit_application
        self.state = "Starting"
        self.message = "Preparing local speech recognition…"
        self.can_copy = False

        node_info = Gio.DBusNodeInfo.new_for_xml(CONTROL_XML)
        interface_info = node_info.lookup_interface(CONTROL_INTERFACE)
        if interface_info is None:
            raise RuntimeError("Could not load the SpeakText D-Bus interface")
        self.registration_id = connection.register_object(
            CONTROL_PATH,
            interface_info,
            self._on_method_call,
            None,
            None,
        )

    def update(self, state: str, message: str, can_copy: bool) -> None:
        current = (self.state, self.message, self.can_copy)
        replacement = (state, message, can_copy)
        if current == replacement:
            return
        self.state, self.message, self.can_copy = replacement
        self.connection.emit_signal(
            None,
            CONTROL_PATH,
            CONTROL_INTERFACE,
            "StatusChanged",
            GLib.Variant("(ssb)", replacement),
        )

    def close(self) -> None:
        if self.registration_id:
            self.connection.unregister_object(self.registration_id)
            self.registration_id = 0

    def _on_method_call(
        self,
        _connection: Gio.DBusConnection,
        _sender: str,
        _object_path: str,
        _interface_name: str,
        method_name: str,
        _parameters: GLib.Variant,
        invocation: Gio.DBusMethodInvocation,
    ) -> None:
        if method_name == "GetStatus":
            invocation.return_value(
                GLib.Variant("(ssb)", (self.state, self.message, self.can_copy))
            )
        elif method_name == "ActivateWindow":
            invocation.return_value(None)
            GLib.idle_add(self._run_void_callback, self.activate_window)
        elif method_name == "CopyLastTranscript":
            invocation.return_value(
                GLib.Variant("(b)", (bool(self.copy_last_transcript()),))
            )
        elif method_name == "CancelRecording":
            invocation.return_value(None)
            GLib.idle_add(self._run_void_callback, self.cancel_recording)
        elif method_name == "Quit":
            invocation.return_value(None)
            GLib.idle_add(self._run_void_callback, self.quit_application)
        else:
            invocation.return_dbus_error(
                f"{CONTROL_INTERFACE}.UnknownMethod",
                f"Unknown SpeakText method: {method_name}",
            )

    @staticmethod
    def _run_void_callback(callback: Callable[[], None]) -> bool:
        callback()
        return GLib.SOURCE_REMOVE
