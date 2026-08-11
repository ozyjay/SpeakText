from __future__ import annotations

import os
from pathlib import Path

APP_ID = "local.SpeakText"
APP_NAME = "SpeakText"
MODEL_NAME = "ggml-base.en.bin"
MODEL_URL = (
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/"
    "ggml-base.en.bin"
)

# SHA-256 published for the upstream ggml-base.en.bin artefact. Keeping the
# digest in source prevents a compromised or incomplete download being loaded.
MODEL_SHA256 = "a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002"

MAX_RECORDING_SECONDS = 120
MIN_RECORDING_SECONDS = 0.3
PREVIEW_INTERVAL_SECONDS = 2.5
SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH = 2


def _xdg_path(variable: str, fallback: str) -> Path:
    value = os.environ.get(variable)
    if value:
        return Path(value)
    return Path.home() / fallback


DATA_DIR = _xdg_path("XDG_DATA_HOME", ".local/share") / "speaktext"
CONFIG_DIR = _xdg_path("XDG_CONFIG_HOME", ".config") / "speaktext"
STATE_DIR = _xdg_path("XDG_STATE_HOME", ".local/state") / "speaktext"
MODEL_PATH = DATA_DIR / "models" / MODEL_NAME
LOG_PATH = STATE_DIR / "speaktext.log"


def worker_path() -> Path:
    override = os.environ.get("SPEAKTEXT_WORKER")
    if override:
        return Path(override)

    installed = Path.home() / ".local/libexec/speaktext/speaktext-worker"
    if installed.is_file():
        return installed

    return Path(__file__).resolve().parents[2] / "build/speaktext-worker"
