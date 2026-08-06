from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from .constants import CONFIG_PATH


@dataclass(slots=True)
class Settings:
    remote_desktop_restore_token: str | None = None
    shortcut_mode: str = "push-to-talk"


class SettingsStore:
    def __init__(self, path: Path = CONFIG_PATH) -> None:
        self.path = path

    def load(self) -> Settings:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return Settings()
        except (OSError, json.JSONDecodeError):
            return Settings()

        return Settings(
            remote_desktop_restore_token=raw.get("remote_desktop_restore_token"),
            shortcut_mode=raw.get("shortcut_mode", "push-to-talk"),
        )

    def save(self, settings: Settings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(asdict(settings), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        temporary.replace(self.path)

