from __future__ import annotations

import os


PREVIEW: dict[str, tuple[str, str]] = {}
for _ext, _mime in {
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp",
    "avif": "image/avif", "ico": "image/x-icon", "svg": "image/svg+xml",
}.items():
    PREVIEW[_ext] = ("image", _mime)
for _ext, _mime in {
    "mp4": "video/mp4", "m4v": "video/mp4", "webm": "video/webm",
    "ogv": "video/ogg", "mov": "video/quicktime", "mkv": "video/x-matroska",
}.items():
    PREVIEW[_ext] = ("video", _mime)
for _ext, _mime in {
    "mp3": "audio/mpeg", "wav": "audio/wav", "ogg": "audio/ogg",
    "oga": "audio/ogg", "opus": "audio/ogg", "m4a": "audio/mp4",
    "aac": "audio/aac", "flac": "audio/flac",
}.items():
    PREVIEW[_ext] = ("audio", _mime)
PREVIEW["pdf"] = ("pdf", "application/pdf")
for _ext in (
    "txt md markdown log csv tsv json xml yaml yml ini cfg conf toml py js mjs ts tsx jsx "
    "dart html htm css scss c h cpp hpp cs java kt go rs rb php sh bat cmd ps1 sql "
    "gradle properties srt vtt"
).split():
    PREVIEW[_ext] = ("text", "text/plain; charset=utf-8")

DOC_EXTS = set("doc docx xls xlsx ppt pptx rtf odt ods odp".split())
ARCHIVE_EXTS = set("zip rar 7z gz tar bz2 xz".split())
THUMB_EXTS = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}


def file_ext(name: str) -> str:
    return os.path.splitext(name)[1].lstrip(".").lower()


def kind_of(name: str) -> str:
    ext = file_ext(name)
    if ext in PREVIEW:
        return PREVIEW[ext][0]
    if ext in DOC_EXTS:
        return "doc"
    if ext in ARCHIVE_EXTS:
        return "archive"
    return "other"


def fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return str(n)


def looks_like_text(data: bytes) -> bool:
    sample = data[:8192]
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8-sig")
    except UnicodeDecodeError:
        return False
    bad = sum(1 for b in sample if b < 32 and b not in (9, 10, 13))
    return bad <= max(4, len(sample) // 100)

