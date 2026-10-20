from __future__ import annotations

import time


PLACEHOLDER_PASSWORD = "change-this-long-password"
PLACEHOLDER_EMAIL = "you@example.com"

SKIP_DIRS = {
    "$RECYCLE.BIN", "System Volume Information", "RECYCLER",
    "__pycache__", ".git", "node_modules",
}

COOKIE_NAME = "fs_session"
SESSION_IDLE_SECONDS = 5 * 60
SESSION_MAX_SECONDS = 24 * 3600
QR_TOKEN_SECONDS = 5 * 60
MAX_LOGIN_FAILURES = 5
LOGIN_LOCK_SECONDS = 15 * 60
SEARCH_MAX_SCANNED = 15000
SEARCH_MAX_RESULTS = 500
CHUNK = 256 * 1024
LOG_MAX_BYTES = 5 * 1024 * 1024

TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off", ""}
AUTH_MODES = {"qr", "password", "both"}

UPLOAD_DEFAULT_MAX_MB = 1000
UPLOAD_MAX_CAP_MB = 1000
UPLOAD_BODY_OVERHEAD = 64 * 1024
UPLOAD_DEFAULT_EXTS = tuple(
    "pdf png jpg jpeg gif webp bmp mp4 m4v mov webm mkv ogv txt md csv json "
    "docx xlsx pptx rtf odt ods odp".split()
)
UPLOAD_TEXT_EXTS = {"txt", "md", "csv", "log", "json", "xml", "yaml", "yml"}
UPLOAD_ZIP_EXTS = {"docx", "xlsx", "pptx", "odt", "ods", "odp"}
UPLOAD_VIDEO_EXTS = {"mp4", "m4v", "mov", "webm", "mkv", "ogv"}
UPLOAD_RATE_WINDOW_SECONDS = 60
UPLOAD_MAX_REQUESTS_PER_WINDOW = 12
UPLOAD_QUOTA_WINDOW_SECONDS = 10 * 60
UPLOAD_QUOTA_BYTES = 500 * 1024 * 1024

WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}

CSP = ("default-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; "
       "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
INLINE_SVG_CSP = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
START_TIME = time.time()

