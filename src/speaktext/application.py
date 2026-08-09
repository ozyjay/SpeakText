from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from .audio import AudioCapture
from .build_info import BUILD_LABEL
from .constants import (
    APP_ID,
    APP_NAME,
    worker_path,
)
from .control import ControlService
from .coordinator import DictationCoordinator, DictationState
from .ibus import IBusTextInjector, IBusTextService
from .injector import ClipboardFallback
from .logging_config import configure_logging
from .model import ModelManager
from .settings import GestureKey, SettingsStore
from .worker import TranscriptionWorker

LOGGER = logging.getLogger(__name__)
StatusNotification = tuple[str, str, str]


def status_notification(
    state: DictationState, message: str
) -> StatusNotification | None:
    if state is DictationState.ERROR:
        return ("dictation-error", "SpeakText error", message)
    if message == "Text copied; paste it at the cursor":
        return ("dictation-result", APP_NAME, message)
    return None


class SpeakTextApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.loop = asyncio.new_event_loop()
        self._pump_source: int | None = None
        self.window: Adw.ApplicationWindow | None = None
        self.status_row: Adw.ActionRow | None = None
        self.status_label: Gtk.Label | None = None
        self.shortcut_label: Gtk.Label | None = None
        self.cancel_shortcut_label: Gtk.Label | None = None
        self.gesture_key_row: Adw.ComboRow | None = None
        self.progress: Gtk.ProgressBar | None = None
        self.copy_button: Gtk.Button | None = None
        self.cancel_button: Gtk.Button | None = None
        self.retry_button: Gtk.Button | None = None
        self.test_button: Gtk.Button | None = None
        self.clear_test_button: Gtk.Button | None = None
        self.test_result_label: Gtk.Label | None = None
        self._test_transcript: str | None = None
        self.model_manager = ModelManager()
        self.ibus_service: IBusTextService | None = None
        self.coordinator: DictationCoordinator | None = None
        self.control_service: ControlService | None = None
        self._model_task: asyncio.Task[None] | None = None
        self._current_state = DictationState.STARTING
        self._current_message = "Preparing local speech recognition…"
        self._startup_progress_text = "Checking model"
        self._startup_progress_fraction: float | None = 0.0
        self._startup_progress_pulsing = False
        self._progress_pulse_source: int | None = None
        self._model_download_started = False
        self._model_download_complete = False
        self.settings_store = SettingsStore()
        self.gesture_key = self.settings_store.load_gesture_key()

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        configure_logging()
        self.hold()
        self._pump_source = GLib.timeout_add(10, self._pump_asyncio)

        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_args: self.quit())
        self.add_action(quit_action)

        connection = self.get_dbus_connection()
        if connection is not None:
            self.control_service = ControlService(
                connection,
                self.activate,
                self._copy_last_transcript,
                self._cancel_recording,
                self.quit,
            )

        GLib.idle_add(self._initialise_services)

    def do_activate(self) -> None:
        if self.window is None:
            self.window = self._build_window()
        self.window.present()

    def _build_window(self) -> Adw.ApplicationWindow:
        window = Adw.ApplicationWindow(application=self)
        window.set_title(APP_NAME)
        window.set_default_size(520, 380)
        window.connect("close-request", self._hide_window)

        header = Adw.HeaderBar()
        title = Adw.WindowTitle(title=APP_NAME, subtitle="Private local dictation")
        header.set_title_widget(title)

        status_group = Adw.PreferencesGroup(title="Status")
        status_row = Adw.ActionRow(title="Starting")
        self.status_row = status_row
        self.status_label = Gtk.Label(label="Preparing local speech recognition…")
        self.status_label.set_wrap(True)
        self.status_label.set_xalign(1)
        self.status_label.set_max_width_chars(35)
        status_row.add_suffix(self.status_label)
        status_group.add(status_row)

        self.progress = Gtk.ProgressBar(show_text=True)
        self.progress.set_text("Checking model")
        status_group.add(self.progress)

        shortcut_group = Adw.PreferencesGroup(title="Dictation")
        self.gesture_key_row = Adw.ComboRow(
            title="Gesture key",
            subtitle="Choose the modifier used to control dictation",
            model=Gtk.StringList.new([key.label for key in GestureKey]),
        )
        self.gesture_key_row.set_selected(list(GestureKey).index(self.gesture_key))
        self.gesture_key_row.connect("notify::selected", self._gesture_key_changed)
        shortcut_group.add(self.gesture_key_row)

        gesture_label = self.gesture_key.label
        shortcut_row = Adw.ActionRow(
            title="Dictation gesture",
            subtitle="Double-tap either selected key to start or finish recording",
        )
        self.shortcut_label = Gtk.Label(
            label=f"{gesture_label}, {gesture_label}"
        )
        shortcut_row.add_suffix(self.shortcut_label)
        shortcut_group.add(shortcut_row)

        cancel_shortcut_row = Adw.ActionRow(
            title="Cancel gesture",
            subtitle="Tap either selected key once while recording",
        )
        self.cancel_shortcut_label = Gtk.Label(label=gesture_label)
        cancel_shortcut_row.add_suffix(self.cancel_shortcut_label)
        shortcut_group.add(cancel_shortcut_row)

        privacy_row = Adw.ActionRow(
            title="Local processing",
            subtitle=(
                "Audio is kept in memory and sent only to the local Whisper worker. "
                "Wayland inserts into the cursor focused when transcription finishes."
            ),
        )
        privacy_row.set_subtitle_lines(3)
        shortcut_group.add(privacy_row)

        test_group = Adw.PreferencesGroup(title="Test dictation")
        test_row = Adw.ActionRow(
            title="Microphone test",
            subtitle="Speak a short sample, then stop recording to view it here.",
        )
        self.test_button = Gtk.Button(label="Start test")
        self.test_button.set_sensitive(False)
        self.test_button.connect(
            "clicked", lambda *_args: self._start_or_stop_test()
        )
        test_row.add_suffix(self.test_button)
        test_group.add(test_row)

        test_result_row = Adw.ActionRow(
            title="Test result",
            subtitle="Shown only in this window until cleared, replaced, or SpeakText exits.",
        )
        self.test_result_label = Gtk.Label(label="No test transcript yet")
        self.test_result_label.set_wrap(True)
        self.test_result_label.set_selectable(True)
        self.test_result_label.set_xalign(0)
        self.test_result_label.set_max_width_chars(35)
        test_result_row.add_suffix(self.test_result_label)
        test_group.add(test_result_row)

        self.clear_test_button = Gtk.Button(label="Clear test result")
        self.clear_test_button.set_sensitive(False)
        self.clear_test_button.connect(
            "clicked", lambda *_args: self._clear_test_transcript()
        )
        test_result_row.add_suffix(self.clear_test_button)

        diagnostics_group = Adw.PreferencesGroup(title="Diagnostics")
        diagnostics_group.add(
            Adw.ActionRow(title="Build", subtitle=BUILD_LABEL)
        )

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        actions.set_halign(Gtk.Align.END)
        self.retry_button = Gtk.Button(label="Retry setup")
        self.retry_button.set_sensitive(False)
        self.retry_button.connect("clicked", lambda *_args: self._retry_setup())
        actions.append(self.retry_button)
        self.cancel_button = Gtk.Button(label="Cancel recording")
        self.cancel_button.set_sensitive(False)
        self.cancel_button.connect(
            "clicked", lambda *_args: self._cancel_recording()
        )
        actions.append(self.cancel_button)
        self.copy_button = Gtk.Button(label="Copy last transcript")
        self.copy_button.set_sensitive(False)
        self.copy_button.connect("clicked", lambda *_args: self._copy_last_transcript())
        actions.append(self.copy_button)
        quit_button = Gtk.Button(label="Quit")
        quit_button.connect("clicked", lambda *_args: self.quit())
        actions.append(quit_button)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        content.set_margin_top(18)
        content.set_margin_bottom(18)
        content.set_margin_start(18)
        content.set_margin_end(18)
        content.append(status_group)
        content.append(shortcut_group)
        content.append(test_group)
        content.append(diagnostics_group)
        content.append(actions)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(content)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(scroll)
        window.set_content(toolbar)
        self._set_status(self._current_state, self._current_message)
        self._refresh_startup_progress()
        if self._startup_progress_pulsing:
            self._start_progress_pulse()
        return window

    def _hide_window(self, window: Adw.ApplicationWindow) -> bool:
        if self.coordinator and self.coordinator.recording_is_test:
            self._cancel_recording()
        self._clear_test_transcript()
        window.set_visible(False)
        return True

    def _initialise_services(self) -> bool:
        try:
            self.ibus_service = IBusTextService(
                self._start_or_stop_recording,
                self._cancel_recording,
                self._is_recording,
                self.gesture_key,
            )
        except (GLib.Error, RuntimeError) as error:
            self._setup_error(f"Could not initialise desktop services: {error}")
            return GLib.SOURCE_REMOVE
        self._model_task = self.loop.create_task(self._prepare_model_and_worker())
        return GLib.SOURCE_REMOVE

    async def _prepare_model_and_worker(self) -> None:
        self._model_download_started = False
        self._model_download_complete = False
        self._set_status(DictationState.STARTING, "Checking local speech model…")
        self._set_startup_progress("This may take a moment")
        self._start_progress_pulse()

        def progress(downloaded: int, total: int | None) -> None:
            GLib.idle_add(self._model_progress, downloaded, total)

        try:
            model_path = await self.model_manager.ensure(progress)
            self._model_download_complete = True
            self._set_status(
                DictationState.STARTING, "Loading local speech recognition…"
            )
            self._set_startup_progress("The first load can take up to 90 seconds")
            self._start_progress_pulse()
            recogniser = TranscriptionWorker(worker_path(), model_path)
            ibus_service = self.ibus_service
            assert ibus_service is not None
            injector = IBusTextInjector(
                ibus_service,
                ClipboardFallback(),
            )
            self.coordinator = DictationCoordinator(
                AudioCapture(),
                recogniser,
                injector,
                self._set_status,
                self._display_test_transcript,
                self.gesture_key.label,
            )
            await self.coordinator.initialise()
            self._stop_progress_pulse()
            self._set_startup_progress("Model ready", fraction=1.0)
            if self.retry_button:
                self.retry_button.set_sensitive(False)
        except Exception as error:
            self.coordinator = None
            self._setup_error(str(error))

    def _model_progress(self, downloaded: int, total: int | None) -> bool:
        if self._model_download_complete:
            return GLib.SOURCE_REMOVE
        if not self._model_download_started:
            self._model_download_started = True
            self._stop_progress_pulse()
            self._set_status(
                DictationState.STARTING, "Downloading local speech model…"
            )
        if total:
            self._set_startup_progress(
                f"Downloading model: {downloaded // (1024 * 1024)} / "
                f"{total // (1024 * 1024)} MiB",
                fraction=min(downloaded / total, 1.0),
            )
        else:
            self._set_startup_progress(
                f"Downloading model: {downloaded // (1024 * 1024)} MiB"
            )
            self._start_progress_pulse()
        return GLib.SOURCE_REMOVE

    def _set_startup_progress(
        self, text: str, fraction: float | None = None
    ) -> None:
        self._startup_progress_text = text
        self._startup_progress_fraction = fraction
        self._refresh_startup_progress()

    def _refresh_startup_progress(self) -> None:
        if not self.progress:
            return
        self.progress.set_fraction(self._startup_progress_fraction or 0.0)
        self.progress.set_text(self._startup_progress_text)

    def _start_progress_pulse(self) -> None:
        self._startup_progress_pulsing = True
        if not self.progress:
            return
        self.progress.pulse()
        if self._progress_pulse_source is None:
            self._progress_pulse_source = GLib.timeout_add(120, self._pulse_progress)

    def _pulse_progress(self) -> bool:
        if self.progress is None:
            self._progress_pulse_source = None
            return GLib.SOURCE_REMOVE
        self.progress.pulse()
        return GLib.SOURCE_CONTINUE

    def _stop_progress_pulse(self) -> None:
        self._startup_progress_pulsing = False
        if self._progress_pulse_source is not None:
            GLib.source_remove(self._progress_pulse_source)
            self._progress_pulse_source = None

    def _is_recording(self) -> bool:
        return bool(
            self.coordinator
            and self.coordinator.state is DictationState.RECORDING
        )

    def _gesture_key_changed(
        self, row: Adw.ComboRow, _parameter: object
    ) -> None:
        gesture_keys = list(GestureKey)
        selected = row.get_selected()
        if selected >= len(gesture_keys):
            return
        gesture_key = gesture_keys[selected]
        if gesture_key is self.gesture_key:
            return
        self.gesture_key = gesture_key
        if self.ibus_service:
            self.ibus_service.set_gesture_key(gesture_key)
        try:
            self.settings_store.save_gesture_key(gesture_key)
        except OSError as error:
            LOGGER.warning(
                "Could not save gesture setting: %s", type(error).__name__
            )
        self._refresh_gesture_labels()
        if (
            self._current_state is DictationState.READY
            and self._current_message.startswith("Double-tap ")
        ):
            self._set_status(
                DictationState.READY,
                f"Double-tap {gesture_key.label} to dictate",
            )

    def _refresh_gesture_labels(self) -> None:
        label = self.gesture_key.label
        if self.shortcut_label:
            self.shortcut_label.set_label(f"{label}, {label}")
        if self.cancel_shortcut_label:
            self.cancel_shortcut_label.set_label(label)

    def _start_or_stop_recording(self) -> None:
        if not self.coordinator:
            return
        if self.coordinator.state is DictationState.RECORDING:
            self.loop.create_task(self.coordinator.deactivate())
        else:
            self.loop.create_task(self.coordinator.activate())

    def _start_or_stop_test(self) -> None:
        if not self.coordinator:
            return
        if self.coordinator.state is DictationState.RECORDING:
            if self.test_button:
                self.test_button.set_sensitive(False)
            self.loop.create_task(self.coordinator.deactivate())
            return
        if self.coordinator.state is DictationState.READY:
            self._clear_test_transcript()
            if self.test_button:
                self.test_button.set_sensitive(False)
            self.loop.create_task(self.coordinator.activate(test=True))

    def _display_test_transcript(self, transcript: str) -> None:
        self._test_transcript = transcript
        if self.test_result_label:
            self.test_result_label.set_label(transcript)
        if self.clear_test_button:
            self.clear_test_button.set_sensitive(True)

    def _clear_test_transcript(self) -> None:
        self._test_transcript = None
        if self.test_result_label:
            self.test_result_label.set_label("No test transcript yet")
        if self.clear_test_button:
            self.clear_test_button.set_sensitive(False)

    def _set_status(self, state: DictationState, message: str) -> None:
        self._current_state = state
        self._current_message = message
        can_copy = bool(self.coordinator and self.coordinator.last_transcript)
        if self.status_row:
            self.status_row.set_title(state.value)
        if self.status_label:
            self.status_label.set_label(message)
        if self.cancel_button:
            self.cancel_button.set_sensitive(state is DictationState.RECORDING)
        if self.gesture_key_row:
            self.gesture_key_row.set_sensitive(
                state is not DictationState.RECORDING
            )
        if self.copy_button:
            self.copy_button.set_sensitive(can_copy)
        if self.test_button:
            test_is_recording = bool(
                self.coordinator and self.coordinator.recording_is_test
            )
            self.test_button.set_sensitive(
                bool(self.coordinator)
                and (state is DictationState.READY or test_is_recording)
            )
            self.test_button.set_label(
                "Stop test"
                if test_is_recording
                else "Start test"
            )
        if self.control_service:
            self.control_service.update(state.value, message, can_copy)

        self.withdraw_notification("dictation-status")
        notification = status_notification(state, message)
        if notification:
            self._notify(*notification)

    def _setup_error(self, message: str) -> None:
        LOGGER.error("setup error: %s", message)
        self._stop_progress_pulse()
        self._set_startup_progress("Setup failed")
        self._set_status(DictationState.ERROR, message)
        if self.retry_button:
            self.retry_button.set_sensitive(True)

    def _retry_setup(self) -> None:
        if self._model_task and not self._model_task.done():
            return
        if self.ibus_service is None:
            try:
                self.ibus_service = IBusTextService(
                    self._start_or_stop_recording,
                    self._cancel_recording,
                    self._is_recording,
                    self.gesture_key,
                )
            except (GLib.Error, RuntimeError) as error:
                self._setup_error(f"Could not initialise IBus: {error}")
                return
        if self.coordinator is None:
            self._model_task = self.loop.create_task(self._prepare_model_and_worker())

    def _cancel_recording(self) -> None:
        if (
            self.coordinator
            and self.coordinator.state is DictationState.RECORDING
        ):
            self.loop.create_task(self.coordinator.cancel_recording())

    def _copy_last_transcript(self) -> bool:
        if not self.coordinator or not self.coordinator.last_transcript:
            return False
        try:
            ClipboardFallback().copy(self.coordinator.last_transcript)
        except Exception as error:
            self._setup_error(f"Could not access the clipboard: {error}")
            return False
        self.coordinator.copied_last_transcript()
        if self.copy_button:
            self.copy_button.set_sensitive(False)
        if self.control_service:
            self.control_service.update(
                self.coordinator.state.value,
                "Transcript copied",
                False,
            )
        return True

    def _notify(self, notification_id: str, title: str, body: str) -> None:
        notification = Gio.Notification.new(title)
        notification.set_body(body)
        self.send_notification(notification_id, notification)

    def _pump_asyncio(self) -> bool:
        if self.loop.is_closed():
            return GLib.SOURCE_REMOVE
        self.loop.call_soon(self.loop.stop)
        self.loop.run_forever()
        return GLib.SOURCE_CONTINUE

    def do_shutdown(self) -> None:
        self._stop_progress_pulse()
        if self._pump_source is not None:
            GLib.source_remove(self._pump_source)
            self._pump_source = None
        if self.coordinator:
            try:
                self.loop.run_until_complete(self.coordinator.shutdown())
            except Exception as error:
                LOGGER.warning("shutdown cleanup failed: %s", error)
        if self.ibus_service:
            self.ibus_service.close()
            self.ibus_service = None
        if self.control_service:
            self.control_service.close()
            self.control_service = None
        pending = asyncio.all_tasks(self.loop)
        for task in pending:
            task.cancel()
        if pending:
            self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        self.loop.close()
        Adw.Application.do_shutdown(self)


def main(argv: list[str] | None = None) -> int:
    application = SpeakTextApplication()
    return application.run(argv if argv is not None else sys.argv)
