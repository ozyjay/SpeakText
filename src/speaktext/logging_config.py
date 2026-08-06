from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .constants import LOG_PATH


def configure_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    handler = RotatingFileHandler(
        LOG_PATH,
        maxBytes=256 * 1024,
        backupCount=2,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)

