from __future__ import annotations

import configparser
import logging
import os
from enum import Enum
from pathlib import Path

from .constants import CONFIG_DIR

LOGGER = logging.getLogger(__name__)


class GestureKey(Enum):
    SHIFT = "shift"
    CONTROL = "control"

    @property
    def label(self) -> str:
        return self.value.title()


class SettingsStore:
    def __init__(self, path: Path = CONFIG_DIR / "settings.ini") -> None:
        self.path = path

    def load_gesture_key(self) -> GestureKey:
        parser = configparser.ConfigParser()
        try:
            with self.path.open(encoding="utf-8") as settings_file:
                parser.read_file(settings_file)
            return GestureKey(parser.get("dictation", "gesture_key"))
        except FileNotFoundError:
            return GestureKey.SHIFT
        except (configparser.Error, KeyError, ValueError, OSError) as error:
            LOGGER.warning(
                "Could not load gesture setting (%s); using Shift",
                type(error).__name__,
            )
            return GestureKey.SHIFT

    def save_gesture_key(self, gesture_key: GestureKey) -> None:
        parser = configparser.ConfigParser()
        parser["dictation"] = {"gesture_key": gesture_key.value}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(".tmp")
        try:
            with temporary_path.open("w", encoding="utf-8") as settings_file:
                parser.write(settings_file)
            os.replace(temporary_path, self.path)
        except OSError:
            temporary_path.unlink(missing_ok=True)
            raise
