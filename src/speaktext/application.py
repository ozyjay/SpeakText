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
from .config import SettingsStore
from .constants import APP_ID, APP_NAME, MODEL_PATH, SHORTCUT_TRIGGER, worker_path
from .control import ControlService
from .coordinator import DictationCoordinator, DictationState
from .injector import ClipboardFallback, TextInjector
from .logging_config import configure_logging
from .model import ModelManager
from .portals import GlobalShortcutPortal, KeyboardPortal, PortalError
from .worker import TranscriptionWorker

LOGGER = logging.getLogger(__name__)


class SpeakTextApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.loop = asyncio.new_event_loop()
        self._pump_source: int | None = None
        self.window: Adw.ApplicationWindow | None = None
        self.status_label: Gtk.Label | None = None
        self.shortcut_label: Gtk.Label | None = None
        self.progress: Gtk.ProgressBar | None = None
        self.copy_button: Gtk.Button | None = None
        self.retry_button: Gtk.Button | None = None
        self.mode_switch: Adw.SwitchRow | None = None
        self.settings_store = SettingsStore()
        self.settings = self.settings_store.load()
        self.model_manager = ModelManager()
        self.shortcut_portal: GlobalShortcutPortal | None = None
        self.keyboard_portal: KeyboardPortal | None = None
        self.coordinator: DictationCoordinator | None = None
        self.control_service: ControlService | None = None
        self._model_task: asyncio.Task[None] | None = None
        self._shortcut_failed = False

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
        shortcut_row = Adw.ActionRow(
            title="Push-to-talk shortcut",
            subtitle="Hold to record; release to transcribe and insert",
        )
        self.shortcut_label = Gtk.Label(label=SHORTCUT_TRIGGER)
        shortcut_row.add_suffix(self.shortcut_label)
        shortcut_group.add(shortcut_row)

        self.mode_switch = Adw.SwitchRow(
            title="Toggle-mode fallback",
            subtitle=(
                "Press once to start and again to stop if the compositor does "
                "not report shortcut release"
            ),
        )
        self.mode_switch.set_active(self.settings.shortcut_mode == "toggle")
        self.mode_switch.connect("notify::active", self._shortcut_mode_changed)
        shortcut_group.add(self.mode_switch)

        privacy_row = Adw.ActionRow(
            title="Local processing",
            subtitle=(
                "Audio is kept in memory and sent only to the local Whisper worker. "
                "Wayland inserts into the cursor focused when transcription finishes."
            ),
        )
        privacy_row.set_subtitle_lines(3)
        shortcut_group.add(privacy_row)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        actions.set_halign(Gtk.Align.END)
        self.retry_button = Gtk.Button(label="Retry setup")
        self.retry_button.set_sensitive(False)
        self.retry_button.connect("clicked", lambda *_args: self._retry_setup())
        actions.append(self.retry_button)
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
        content.append(actions)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(content)
        window.set_content(toolbar)
        return window

    @staticmethod
    def _hide_window(window: Adw.ApplicationWindow) -> bool:
        window.set_visible(False)
        return True

    def _initialise_services(self) -> bool:
        try:
            self.shortcut_portal = GlobalShortcutPortal()
            self.keyboard_portal = KeyboardPortal()
        except GLib.Error as error:
            self._setup_error(f"Could not connect to desktop portals: {error.message}")
            return GLib.SOURCE_REMOVE

        self.shortcut_portal.initialise(
            self._shortcut_activated,
            self._shortcut_deactivated,
            self._shortcut_ready,
            self._shortcut_error,
        )
        self.keyboard_portal.initialise(
            self.settings.remote_desktop_restore_token,
            self._keyboard_ready,
            self._keyboard_unavailable,
        )
        self._model_task = self.loop.create_task(self._prepare_model_and_worker())
        return GLib.SOURCE_REMOVE

    async def _prepare_model_and_worker(self) -> None:
        self._set_status(DictationState.STARTING, "Downloading or checking speech model…")

        def progress(downloaded: int, total: int | None) -> None:
            GLib.idle_add(self._model_progress, downloaded, total)

        try:
            model_path = await self.model_manager.ensure(progress)
            recogniser = TranscriptionWorker(worker_path(), model_path)
            keyboard = self.keyboard_portal
            assert keyboard is not None
            injector = TextInjector(keyboard, ClipboardFallback())
            self.coordinator = DictationCoordinator(
                AudioCapture(), recogniser, injector, self._set_status
            )
            await self.coordinator.initialise()
            if self.progress:
                self.progress.set_fraction(1.0)
                self.progress.set_text("Model ready")
            if self.retry_button and not self._shortcut_failed:
                self.retry_button.set_sensitive(False)
        except Exception as error:
            self.coordinator = None
            self._setup_error(str(error))

    def _model_progress(self, downloaded: int, total: int | None) -> bool:
        if self.progress:
            if total:
                self.progress.set_fraction(min(downloaded / total, 1.0))
                self.progress.set_text(
                    f"Downloading model: {downloaded // (1024 * 1024)} / "
                    f"{total // (1024 * 1024)} MiB"
                )
            else:
                self.progress.pulse()
                self.progress.set_text(
                    f"Downloading model: {downloaded // (1024 * 1024)} MiB"
                )
        return GLib.SOURCE_REMOVE

    def _shortcut_ready(self, description: str) -> None:
        LOGGER.info("global shortcut ready")
        self._shortcut_failed = False
        if self.shortcut_label:
            self.shortcut_label.set_label(description)
        if self.retry_button and self.coordinator is not None:
            self.retry_button.set_sensitive(False)

    def _keyboard_ready(self, restore_token: str | None) -> None:
        LOGGER.info("keyboard portal ready")
        if restore_token:
            self.settings.remote_desktop_restore_token = restore_token
            self.settings_store.save(self.settings)

    def _keyboard_unavailable(self, error: Exception) -> None:
        LOGGER.warning("keyboard portal unavailable: %s", error)
        self._notify(
            "keyboard-permission",
            "Clipboard fallback enabled",
            "Keyboard permission was not granted; transcripts will be copied instead.",
        )

    def _shortcut_error(self, error: Exception) -> None:
        self._shortcut_failed = True
        self._setup_error(f"Shortcut unavailable: {error}")

    def _shortcut_activated(self) -> None:
        if self.coordinator:
            if (
                self.settings.shortcut_mode == "toggle"
                and self.coordinator.state is DictationState.RECORDING
            ):
                self.loop.create_task(self.coordinator.deactivate())
            else:
                self.loop.create_task(self.coordinator.activate())

    def _shortcut_deactivated(self) -> None:
        if self.coordinator and self.settings.shortcut_mode != "toggle":
            self.loop.create_task(self.coordinator.deactivate())

    def _shortcut_mode_changed(self, switch: Adw.SwitchRow, _property: object) -> None:
        self.settings.shortcut_mode = "toggle" if switch.get_active() else "push-to-talk"
        self.settings_store.save(self.settings)

    def _set_status(self, state: DictationState, message: str) -> None:
        can_copy = bool(self.coordinator and self.coordinator.last_transcript)
        if self.status_label:
            self.status_label.set_label(message)
        if self.copy_button:
            self.copy_button.set_sensitive(can_copy)
        if self.control_service:
            self.control_service.update(state.value, message, can_copy)

        if state in {
            DictationState.RECORDING,
            DictationState.TRANSCRIBING,
            DictationState.INSERTING,
        }:
            self._notify("dictation-status", state.value, message)
        else:
            self.withdraw_notification("dictation-status")
            if state is DictationState.ERROR:
                self._notify("dictation-error", "SpeakText error", message)
            elif message in {"Text inserted", "Text copied; paste it at the cursor"}:
                self._notify("dictation-result", APP_NAME, message)

    def _setup_error(self, message: str) -> None:
        LOGGER.error("setup error: %s", message)
        self._set_status(DictationState.ERROR, message)
        if self.retry_button:
            self.retry_button.set_sensitive(True)

    def _retry_setup(self) -> None:
        if self._model_task and not self._model_task.done():
            return
        if self._shortcut_failed:
            if self.shortcut_portal:
                self.shortcut_portal.close()
            try:
                self.shortcut_portal = GlobalShortcutPortal()
                self.shortcut_portal.initialise(
                    self._shortcut_activated,
                    self._shortcut_deactivated,
                    self._shortcut_ready,
                    self._shortcut_error,
                )
            except GLib.Error as error:
                self._shortcut_error(error)
        if self.coordinator is None:
            self._model_task = self.loop.create_task(self._prepare_model_and_worker())

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
        if self._pump_source is not None:
            GLib.source_remove(self._pump_source)
            self._pump_source = None
        if self.coordinator:
            try:
                self.loop.run_until_complete(self.coordinator.shutdown())
            except Exception as error:
                LOGGER.warning("shutdown cleanup failed: %s", error)
        if self.shortcut_portal:
            self.shortcut_portal.close()
        if self.keyboard_portal:
            self.keyboard_portal.close()
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
