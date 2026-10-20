from __future__ import annotations

import os
import re
import threading
from datetime import datetime
from pathlib import Path

from .constants import LOG_MAX_BYTES


_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def clean(value, limit: int = 300) -> str:
    """Make user-controlled text safe for a one-line log entry."""
    text = _CTRL.sub(" ", str(value))
    return text if len(text) <= limit else text[:limit] + "..."


class ActivityLog:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.touch(exist_ok=True)
        except OSError as e:
            print(f"[warn] cannot create log file {path}: {e}", flush=True)

    def write(self, ip: str, event: str, detail: str = "") -> None:
        line = f"{datetime.now():%Y-%m-%d %H:%M:%S} | {ip:<15} | {event:<13} | {clean(detail)}\n"
        with self._lock:
            try:
                if self.path.exists() and self.path.stat().st_size > LOG_MAX_BYTES:
                    os.replace(self.path, self.path.with_name(self.path.stem + ".old" + self.path.suffix))
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write(line)
            except OSError:
                pass

