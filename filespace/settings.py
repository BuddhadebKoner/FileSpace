from __future__ import annotations

import hashlib
import ipaddress
import re
import threading
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from .constants import (
    AUTH_MODES,
    FALSE_VALUES,
    PLACEHOLDER_PASSWORD,
    TRUE_VALUES,
    UPLOAD_DEFAULT_EXTS,
    UPLOAD_DEFAULT_MAX_MB,
    UPLOAD_MAX_CAP_MB,
)
from .uploads import UPLOAD_MIME_BY_EXT


def default_env_template() -> str:
    return files("filespace").joinpath("default.env").read_text(encoding="utf-8")


@dataclass(frozen=True)
class Settings:
    email: str
    password: str
    auth_mode: str
    public: bool
    networks: tuple
    bad_entries: tuple
    candidate_file_upload_enabled: bool
    upload_max_bytes: int
    upload_allowed_exts: tuple[str, ...]
    upload_config_errors: tuple[str, ...]
    fingerprint: str

    @property
    def credentials_ready(self) -> bool:
        return bool(self.email) and bool(self.password) and self.password != PLACEHOLDER_PASSWORD

    @property
    def password_login_enabled(self) -> bool:
        return self.auth_mode in {"password", "both"}

    @property
    def qr_login_enabled(self) -> bool:
        return self.auth_mode in {"qr", "both"}

    @property
    def auth_ready(self) -> bool:
        return self.qr_login_enabled or (self.password_login_enabled and self.credentials_ready)


def parse_env(text: str) -> dict:
    data = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        data[key] = value
    return data


def config_bool(data: dict, key: str, default: bool = False) -> bool:
    raw = data.get(key)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    return default


def parse_upload_max_bytes(data: dict) -> tuple[int, str | None]:
    raw = data.get("FILESPACE_UPLOAD_MAX_MB", str(UPLOAD_DEFAULT_MAX_MB)).strip()
    try:
        mb = int(raw)
    except ValueError:
        return (
            UPLOAD_DEFAULT_MAX_MB * 1024 * 1024,
            f"FILESPACE_UPLOAD_MAX_MB is invalid; using {UPLOAD_DEFAULT_MAX_MB} MB",
        )
    if mb <= 0:
        return (
            UPLOAD_DEFAULT_MAX_MB * 1024 * 1024,
            f"FILESPACE_UPLOAD_MAX_MB must be positive; using {UPLOAD_DEFAULT_MAX_MB} MB",
        )
    if mb > UPLOAD_MAX_CAP_MB:
        return UPLOAD_MAX_CAP_MB * 1024 * 1024, f"FILESPACE_UPLOAD_MAX_MB capped at {UPLOAD_MAX_CAP_MB} MB"
    return mb * 1024 * 1024, None


def parse_upload_exts(data: dict) -> tuple[tuple[str, ...], str | None]:
    raw = data.get("FILESPACE_UPLOAD_ALLOWED_EXTENSIONS", ",".join(UPLOAD_DEFAULT_EXTS))
    values = []
    ignored = []
    for item in re.split(r"[,\s;]+", raw):
        ext = item.strip().lower().lstrip(".")
        if not ext:
            continue
        if ext in UPLOAD_MIME_BY_EXT and ext not in values:
            values.append(ext)
        else:
            ignored.append(ext)
    if not values:
        return UPLOAD_DEFAULT_EXTS, "FILESPACE_UPLOAD_ALLOWED_EXTENSIONS had no supported values; using defaults"
    error = f"ignored unsupported upload extensions: {', '.join(ignored)}" if ignored else None
    return tuple(values), error


def build_settings(data: dict) -> Settings:
    email = data.get("FILESPACE_EMAIL", "").strip()
    password = data.get("FILESPACE_PASSWORD", "")
    auth_mode = data.get("FILESPACE_AUTH_MODE", "qr").strip().lower()
    if auth_mode not in AUTH_MODES:
        auth_mode = "qr"
    public = data.get("FILESPACE_PUBLIC", "false").strip().lower() in TRUE_VALUES
    upload_enabled = config_bool(data, "CANDIDATE_FILE_UPLOAD_ENABLED", False)
    upload_max_bytes, upload_max_error = parse_upload_max_bytes(data)
    upload_allowed_exts, upload_ext_error = parse_upload_exts(data)
    upload_config_errors = tuple(e for e in (upload_max_error, upload_ext_error) if e)
    networks, bad = [], []
    for raw in re.split(r"[,\s;]+", data.get("FILESPACE_ALLOWED_IPS", "")):
        if not raw:
            continue
        try:
            networks.append(ipaddress.ip_network(raw, strict=False))
        except ValueError:
            bad.append(raw)
    fingerprint = hashlib.sha256(f"{auth_mode}\0{email.lower()}\0{password}".encode("utf-8")).hexdigest()
    return Settings(
        email, password, auth_mode, public, tuple(networks), tuple(bad),
        upload_enabled, upload_max_bytes, upload_allowed_exts, upload_config_errors,
        fingerprint,
    )


def describe(s: Settings) -> str:
    if s.public:
        mode = "PUBLIC (any device can reach the login page)"
    else:
        entry = "entry" if len(s.networks) == 1 else "entries"
        mode = f"RESTRICTED ({len(s.networks)} allowed IP {entry}: {', '.join(str(n) for n in s.networks) or 'none'})"
    extra = f" | ignored invalid IPs: {', '.join(s.bad_entries)}" if s.bad_entries else ""
    uploads = "on" if s.candidate_file_upload_enabled else "off"
    return f"{mode} | auth={s.auth_mode} | uploads={uploads}{extra}"


class ConfigStore:
    def __init__(self, path: Path, on_reload=None):
        self.path = path
        self.on_reload = on_reload
        self._mtime = None
        self._lock = threading.Lock()
        self._cur: Settings | None = None
        self.refresh(force=True)

    def refresh(self, force: bool = False) -> None:
        try:
            mtime = self.path.stat().st_mtime_ns
        except OSError:
            return
        if not force and mtime == self._mtime:
            return
        with self._lock:
            if not force and mtime == self._mtime:
                return
            try:
                text = self.path.read_text(encoding="utf-8-sig")
            except OSError:
                return
            first = self._cur is None
            self._cur = build_settings(parse_env(text))
            self._mtime = mtime
            if not first:
                print(f"[config] .env reloaded -> {describe(self._cur)}", flush=True)
                if self.on_reload:
                    self.on_reload(self._cur)

    def get(self) -> Settings:
        self.refresh()
        assert self._cur is not None
        return self._cur


def ensure_env_file(path: Path) -> None:
    if path.exists():
        return
    path.write_text(default_env_template(), encoding="utf-8")
    raise SystemExit(
        f"\nCreated a settings file at: {path}\n"
        "Open it, set FILESPACE_AUTH_MODE, FILESPACE_ALLOWED_IPS, and any password fallback,\n"
        "then run this script again.\n"
    )

