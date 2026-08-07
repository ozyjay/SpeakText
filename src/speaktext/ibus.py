from __future__ import annotations

import logging
from collections.abc import Callable
from enum import Enum
from time import monotonic
from typing import Protocol

import gi

gi.require_version("IBus", "1.0")
from gi.repository import IBus  # noqa: E402
from gi.repository import GLib  # noqa: E402

from .injector import Clipboard, InsertionOutcome, InsertionStatus

LOGGER = logging.getLogger(__name__)
ENGINE_NAME = "speaktext"
COMPONENT_NAME = "local.SpeakText.IBus"
ENGINE_PATH = "/local/SpeakText/IBus/Engine"
SHIFT_TAP_INTERVAL_SECONDS = 0.35


class ShiftTapAction(Enum):
    NONE = "none"
    START_OR_STOP = "start-or-stop"
    SCHEDULE_CANCEL = "schedule-cancel"


class ShiftTapGesture:
    def __init__(self, interval: float = SHIFT_TAP_INTERVAL_SECONDS) -> None:
        self.interval = interval
        self.pending_at: float | None = None

    def tap(self, recording: bool, now: float) -> ShiftTapAction:
        if (
            self.pending_at is not None
            and now - self.pending_at <= self.interval
        ):
            self.pending_at = None
            return ShiftTapAction.START_OR_STOP
        self.pending_at = now
        if recording:
            return ShiftTapAction.SCHEDULE_CANCEL
        return ShiftTapAction.NONE

    def expire(self, recording: bool, now: float) -> bool:
        if self.pending_at is None or now - self.pending_at < self.interval:
            return False
        self.pending_at = None
        return recording

    def reset(self) -> None:
        self.pending_at = None


class TextCommitter(Protocol):
    def commit(self, text: str) -> bool: ...


class SpeakTextEngine(IBus.Engine):
    __gtype_name__ = "SpeakTextIBusEngine"

    def __init__(self, service: IBusTextService, object_path: str) -> None:
        super().__init__(
            engine_name=ENGINE_NAME,
            connection=service.bus.get_connection(),
            object_path=object_path,
        )
        self.service = service
        self.enabled = False
        self.focused = False

    def do_enable(self) -> None:
        self.enabled = True
        self.service.engine_state_changed(self)

    def do_disable(self) -> None:
        self.enabled = False
        self.service.engine_state_changed(self)
        self.service.context_lost()

    def do_focus_in(self) -> None:
        self.focused = True
        self.service.engine_state_changed(self)

    def do_focus_out(self) -> None:
        self.focused = False
        self.service.engine_state_changed(self)
        self.service.context_lost()

    def do_process_key_event(
        self, keyval: int, _keycode: int, state: int
    ) -> bool:
        self.service.process_key_event(keyval, state)
        return False

    def do_destroy(self) -> None:
        self.enabled = False
        self.focused = False
        self.service.engine_state_changed(self)
        super().do_destroy()


class SpeakTextEngineFactory(IBus.Factory):
    def __init__(self, service: IBusTextService) -> None:
        super().__init__(bus=service.bus)
        self.service = service
        self.engine_number = 0

    def do_create_engine(self, engine_name: str) -> IBus.Engine | None:
        if engine_name != ENGINE_NAME:
            return super().do_create_engine(engine_name)
        self.engine_number += 1
        return SpeakTextEngine(
            self.service, f"{ENGINE_PATH}/{self.engine_number}"
        )


class IBusTextService:
    def __init__(
        self,
        on_start_or_stop: Callable[[], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        is_recording: Callable[[], bool] | None = None,
    ) -> None:
        IBus.init()
        self.on_start_or_stop = on_start_or_stop or (lambda: None)
        self.on_cancel = on_cancel or (lambda: None)
        self.is_recording = is_recording or (lambda: False)
        self.shift_gesture = ShiftTapGesture()
        self._cancel_source: int | None = None
        self.bus = IBus.Bus()
        if not self.bus.is_connected():
            raise RuntimeError("Could not connect to IBus")
        self.factory = SpeakTextEngineFactory(self)
        self.active_engine: SpeakTextEngine | None = None
        self.component = self._component()
        if not self.bus.register_component(self.component):
            self.factory.destroy()
            self.bus.destroy()
            raise RuntimeError("Could not register the SpeakText IBus engine")

    @staticmethod
    def _component() -> IBus.Component:
        component = IBus.Component(
            name=COMPONENT_NAME,
            description="SpeakText input method",
            version="1.0",
            license="Unspecified",
            author="SpeakText contributors",
            homepage="",
            command_line="speaktext",
            textdomain="speaktext",
        )
        component.add_engine(
            IBus.EngineDesc(
                name=ENGINE_NAME,
                longname="SpeakText",
                description="Private local speech-to-text dictation",
                language="en",
                license="Unspecified",
                author="SpeakText contributors",
                icon="local.SpeakText",
                layout="default",
                symbol="ST",
                rank=80,
            )
        )
        return component

    def engine_state_changed(self, engine: SpeakTextEngine) -> None:
        if engine.enabled and engine.focused:
            self.active_engine = engine
        elif self.active_engine is engine:
            self.active_engine = None

    def process_key_event(self, keyval: int, state: int) -> None:
        if keyval not in (IBus.KEY_Shift_L, IBus.KEY_Shift_R):
            return
        if not state & int(IBus.ModifierType.RELEASE_MASK):
            return

        action = self.shift_gesture.tap(self.is_recording(), monotonic())
        if action is ShiftTapAction.START_OR_STOP:
            self._clear_cancel_source()
            self.on_start_or_stop()
        elif action is ShiftTapAction.SCHEDULE_CANCEL:
            self._clear_cancel_source()
            self._cancel_source = GLib.timeout_add(
                round(SHIFT_TAP_INTERVAL_SECONDS * 1_000) + 10,
                self._cancel_after_single_tap,
            )

    def _cancel_after_single_tap(self) -> bool:
        self._cancel_source = None
        if self.shift_gesture.expire(self.is_recording(), monotonic()):
            self.on_cancel()
        return GLib.SOURCE_REMOVE

    def _clear_cancel_source(self) -> None:
        if self._cancel_source is not None:
            GLib.source_remove(self._cancel_source)
            self._cancel_source = None

    def reset_shift_gesture(self) -> None:
        self._clear_cancel_source()
        self.shift_gesture.reset()

    def context_lost(self) -> None:
        self.reset_shift_gesture()
        if self.is_recording():
            self.on_cancel()

    def close(self) -> None:
        self.reset_shift_gesture()
        self.active_engine = None
        self.factory.destroy()
        self.bus.destroy()

    def commit(self, text: str) -> bool:
        engine = self.active_engine
        if engine is None:
            return False
        try:
            engine.commit_text(IBus.Text.new_from_string(text))
        except Exception as error:
            LOGGER.warning("IBus text commit failed: %s", type(error).__name__)
            return False
        return True


class IBusTextInjector:
    def __init__(self, committer: TextCommitter, clipboard: Clipboard) -> None:
        self.committer = committer
        self.clipboard = clipboard

    async def insert(self, text: str) -> InsertionOutcome:
        if not text:
            return InsertionOutcome(InsertionStatus.EMPTY)
        if self.committer.commit(text):
            return InsertionOutcome(InsertionStatus.INSERTED, len(text))
        self.clipboard.copy(text)
        return InsertionOutcome(InsertionStatus.COPIED)
