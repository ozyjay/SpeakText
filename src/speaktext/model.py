from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from .constants import MODEL_PATH, MODEL_SHA256, MODEL_URL

LOGGER = logging.getLogger(__name__)
ProgressCallback = Callable[[int, int | None], None]


class ModelError(RuntimeError):
    pass


class ModelManager:
    def __init__(
        self,
        path: Path = MODEL_PATH,
        url: str = MODEL_URL,
        sha256: str = MODEL_SHA256,
    ) -> None:
        self.path = path
        self.url = url
        self.sha256 = sha256.lower()

    async def ensure(self, progress: ProgressCallback | None = None) -> Path:
        return await asyncio.to_thread(self._ensure_sync, progress)

    def verify(self, path: Path | None = None) -> bool:
        candidate = path or self.path
        if not candidate.is_file():
            return False
        digest = hashlib.sha256()
        with candidate.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest() == self.sha256

    def _ensure_sync(self, progress: ProgressCallback | None) -> Path:
        if self.verify():
            LOGGER.info("speech model verified")
            return self.path

        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        partial = self.path.with_suffix(self.path.suffix + ".part")
        try:
            with urllib.request.urlopen(self.url, timeout=30) as response:
                total_header = response.headers.get("Content-Length")
                total = int(total_header) if total_header else None
                written = 0
                digest = hashlib.sha256()
                with partial.open("wb") as output:
                    while chunk := response.read(1024 * 1024):
                        output.write(chunk)
                        digest.update(chunk)
                        written += len(chunk)
                        if progress:
                            progress(written, total)
                if digest.hexdigest() != self.sha256:
                    raise ModelError("Downloaded speech model failed checksum validation")
            os.chmod(partial, 0o600)
            partial.replace(self.path)
        except (OSError, urllib.error.URLError) as error:
            raise ModelError(f"Could not download the speech model: {error}") from error
        finally:
            partial.unlink(missing_ok=True)

        LOGGER.info("speech model downloaded and verified")
        return self.path
