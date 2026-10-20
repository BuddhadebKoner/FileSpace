from __future__ import annotations

import os

from .constants import SKIP_DIRS


def fmt_path(value: str) -> str:
    """Normalize a relative path. parse_qs already URL-decodes the value."""
    return (value or "").replace("\\", "/").strip("/")


def skip_name(name: str) -> bool:
    return name in SKIP_DIRS or name.startswith(".")


def hidden_attr(st: os.stat_result) -> bool:
    attrs = getattr(st, "st_file_attributes", 0)
    return bool(attrs & 0x2 or attrs & 0x4)

