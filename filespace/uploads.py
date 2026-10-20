from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
from collections import deque
from datetime import datetime

from .constants import (
    UPLOAD_TEXT_EXTS,
    UPLOAD_ZIP_EXTS,
    WINDOWS_RESERVED_NAMES,
)
from .filetypes import file_ext, fmt_bytes, looks_like_text
from .fs_utils import skip_name


UPLOAD_MIME_BY_EXT = {
    "pdf": {"application/pdf"},
    "png": {"image/png"},
    "jpg": {"image/jpeg"},
    "jpeg": {"image/jpeg"},
    "gif": {"image/gif"},
    "webp": {"image/webp"},
    "bmp": {"image/bmp", "image/x-ms-bmp"},
    "mp4": {"video/mp4", "application/mp4"},
    "m4v": {"video/mp4", "video/x-m4v", "application/mp4"},
    "mov": {"video/quicktime", "video/mp4"},
    "webm": {"video/webm"},
    "mkv": {"video/x-matroska", "video/webm"},
    "ogv": {"video/ogg", "application/ogg"},
    "txt": {"text/plain"},
    "md": {"text/markdown", "text/plain"},
    "csv": {"text/csv", "application/csv", "text/plain"},
    "json": {"application/json", "text/json", "text/plain"},
    "docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/zip"},
    "xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/zip"},
    "pptx": {"application/vnd.openxmlformats-officedocument.presentationml.presentation", "application/zip"},
    "rtf": {"application/rtf", "text/rtf", "text/plain"},
    "odt": {"application/vnd.oasis.opendocument.text", "application/zip"},
    "ods": {"application/vnd.oasis.opendocument.spreadsheet", "application/zip"},
    "odp": {"application/vnd.oasis.opendocument.presentation", "application/zip"},
}

_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def upload_signature_ok(ext: str, data: bytes) -> bool:
    if ext == "pdf":
        return data.startswith(b"%PDF-")
    if ext in {"jpg", "jpeg"}:
        return data.startswith(b"\xff\xd8\xff")
    if ext == "png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if ext == "gif":
        return data.startswith((b"GIF87a", b"GIF89a"))
    if ext == "webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    if ext == "bmp":
        return data.startswith(b"BM")
    if ext == "rtf":
        return data.lstrip().startswith(b"{\\rtf")
    if ext in {"mp4", "m4v", "mov"}:
        return len(data) >= 12 and data[4:8] == b"ftyp"
    if ext in {"webm", "mkv"}:
        return data.startswith(b"\x1a\x45\xdf\xa3")
    if ext == "ogv":
        return data.startswith(b"OggS")
    if ext in UPLOAD_ZIP_EXTS:
        return data.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"))
    if ext in UPLOAD_TEXT_EXTS:
        if not looks_like_text(data):
            return False
        if ext == "json":
            try:
                json.loads(data.decode("utf-8-sig"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return False
        return True
    return False


def validate_upload_file(filename: str, content_type: str, data: bytes, cfg) -> str:
    ext = file_ext(filename)
    if not ext or ext not in cfg.upload_allowed_exts or ext not in UPLOAD_MIME_BY_EXT:
        raise ValueError("This file type is not allowed.")
    if not data:
        raise ValueError("Uploaded file is empty.")
    if len(data) > cfg.upload_max_bytes:
        raise ValueError(f"File is larger than {fmt_bytes(cfg.upload_max_bytes)}.")
    normalized_type = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized_type and normalized_type != "application/octet-stream":
        if normalized_type not in UPLOAD_MIME_BY_EXT[ext]:
            raise ValueError("The uploaded file content type is not allowed.")
    if not upload_signature_ok(ext, data):
        raise ValueError("The uploaded file content does not match its extension.")
    return ext


def safe_upload_filename(original: str, ext: str) -> str:
    name = original.replace("\\", "/").split("/")[-1]
    stem = os.path.splitext(name)[0]
    stem = _CTRL.sub(" ", stem)
    stem = re.sub(r'[<>:"/\\|?*]+', "_", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" ._")
    if not stem:
        stem = "upload"
    stem = stem[:72].rstrip(" ._") or "upload"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    token = secrets.token_hex(8)
    return f"{stem}-{stamp}-{token}.{ext}"


def validate_folder_name(name: str) -> str:
    value = (name or "").strip()
    if not value:
        raise ValueError("Folder name is required.")
    if len(value) > 120:
        raise ValueError("Folder name is too long.")
    if value in (".", "..") or "/" in value or "\\" in value or ":" in value:
        raise ValueError("Folder name is not allowed.")
    if value.endswith((".", " ")) or value.startswith(".") or skip_name(value):
        raise ValueError("Folder name is not allowed.")
    if re.search(r'[<>:"/\\|?*\x00-\x1f\x7f]', value):
        raise ValueError("Folder name contains invalid characters.")
    if value.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES:
        raise ValueError("Folder name is reserved by Windows.")
    return value


class UploadRateLimiter:
    def __init__(self, max_requests: int, max_bytes: int, window: int):
        self.max_requests = max_requests
        self.max_bytes = max_bytes
        self.window = window
        self._d: dict[str, deque] = {}
        self._lock = threading.Lock()

    def check(self, key: str, size: int) -> int:
        now = time.time()
        cutoff = now - self.window
        with self._lock:
            events = self._d.setdefault(key, deque())
            while events and events[0][0] < cutoff:
                events.popleft()
            used = sum(n for _, n in events)
            if len(events) >= self.max_requests or used + size > self.max_bytes:
                oldest = events[0][0] if events else now
                return max(1, int(oldest + self.window - now))
            events.append((now, size))
            return 0

