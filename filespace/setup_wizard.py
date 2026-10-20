from __future__ import annotations

import getpass
import sys
from pathlib import Path

from .constants import (
    FALSE_VALUES,
    PLACEHOLDER_EMAIL,
    PLACEHOLDER_PASSWORD,
    TRUE_VALUES,
    UPLOAD_DEFAULT_MAX_MB,
    UPLOAD_MAX_CAP_MB,
)
from .settings import default_env_template, parse_env


SETUP_KEYS = [
    "FILESPACE_ROOT",
    "FILESPACE_CREATE_SHORTCUT",
    "FILESPACE_EMAIL",
    "FILESPACE_PASSWORD",
    "FILESPACE_AUTH_MODE",
    "FILESPACE_ALLOWED_IPS",
    "FILESPACE_PUBLIC",
    "CANDIDATE_FILE_UPLOAD_ENABLED",
    "FILESPACE_UPLOAD_MAX_MB",
]


def can_prompt() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _bool_from_env(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    return default


def _yes_no(question: str, default: bool) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    while True:
        raw = input(question + suffix).strip().lower()
        if not raw:
            return default
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        print("Please answer Y or N.")


def _text(question: str, default: str = "", required: bool = False) -> str:
    suffix = f" [{default}]: " if default else ": "
    while True:
        raw = input(question + suffix).strip()
        value = raw if raw else default
        value = value.strip().strip("\"'")
        if value or not required:
            return value
        print("This value is required.")


def _password(default: str = "") -> str:
    keep_existing = bool(default and default != PLACEHOLDER_PASSWORD)
    prompt = "FILESPACE_PASSWORD [press Enter to keep existing]: " if keep_existing else "FILESPACE_PASSWORD: "
    while True:
        value = getpass.getpass(prompt)
        if value:
            return value
        if keep_existing:
            return default
        print("Password is required for password login.")


def _path(question: str, default: str) -> str:
    while True:
        value = _text(question, default, required=True)
        target = Path(value).expanduser()
        if target.is_dir():
            return str(target)
        print(f"Path does not exist or is not a folder: {value}")


def _upload_limit(default: str | None) -> str:
    current = str(default or UPLOAD_DEFAULT_MAX_MB)
    use_default = _yes_no(f"Use default FILESPACE_UPLOAD_MAX_MB={UPLOAD_DEFAULT_MAX_MB}?", True)
    if use_default:
        return str(UPLOAD_DEFAULT_MAX_MB)
    while True:
        raw = _text(f"Custom FILESPACE_UPLOAD_MAX_MB (1-{UPLOAD_MAX_CAP_MB})", current, required=True)
        try:
            value = int(raw)
        except ValueError:
            print("Please enter a whole number.")
            continue
        if 1 <= value <= UPLOAD_MAX_CAP_MB:
            return str(value)
        print(f"Please enter a value from 1 to {UPLOAD_MAX_CAP_MB}.")


def _update_env_text(text: str, updates: dict[str, str]) -> str:
    remaining = dict(updates)
    lines = text.splitlines()
    out = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            out.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in remaining:
            out.append(f"{key}={remaining.pop(key)}")
        else:
            out.append(line)
    if remaining:
        if out and out[-1].strip():
            out.append("")
        for key in SETUP_KEYS:
            if key in remaining:
                out.append(f"{key}={remaining.pop(key)}")
        for key, value in remaining.items():
            out.append(f"{key}={value}")
    return "\n".join(out).rstrip() + "\n"


def run_setup_wizard(env_path: Path, root_override: str | None = None) -> dict[str, str]:
    if env_path.exists():
        text = env_path.read_text(encoding="utf-8-sig")
    else:
        text = default_env_template()
        env_path.parent.mkdir(parents=True, exist_ok=True)

    data = parse_env(text)
    print("")
    print("FileSpace setup - answers will be saved to .env before the server starts.")
    print("Press Enter to keep the shown default.")
    print("")

    updates: dict[str, str] = {}
    root_default = root_override or data.get("FILESPACE_ROOT", "D:\\")
    updates["FILESPACE_ROOT"] = _path("FILESPACE_ROOT", root_default)
    updates["FILESPACE_CREATE_SHORTCUT"] = str(
        _yes_no("FILESPACE_CREATE_SHORTCUT", _bool_from_env(data.get("FILESPACE_CREATE_SHORTCUT"), False))
    ).lower()

    use_qr = _yes_no("Use QR login? This sets FILESPACE_AUTH_MODE=qr", data.get("FILESPACE_AUTH_MODE", "qr") != "password")
    if use_qr:
        updates["FILESPACE_AUTH_MODE"] = "qr"
    else:
        updates["FILESPACE_AUTH_MODE"] = "password"
        updates["FILESPACE_EMAIL"] = _text(
            "FILESPACE_EMAIL",
            "" if data.get("FILESPACE_EMAIL") == PLACEHOLDER_EMAIL else data.get("FILESPACE_EMAIL", ""),
            required=True,
        )
        updates["FILESPACE_PASSWORD"] = _password(data.get("FILESPACE_PASSWORD", ""))

    is_public = _yes_no("FILESPACE_PUBLIC", _bool_from_env(data.get("FILESPACE_PUBLIC"), False))
    updates["FILESPACE_PUBLIC"] = str(is_public).lower()
    if is_public:
        updates["FILESPACE_ALLOWED_IPS"] = ""
    else:
        updates["FILESPACE_ALLOWED_IPS"] = _text(
            "FILESPACE_ALLOWED_IPS (comma-separated IPs/CIDR; blank means only this PC)",
            data.get("FILESPACE_ALLOWED_IPS", ""),
            required=False,
        )

    uploads_enabled = _yes_no(
        "CANDIDATE_FILE_UPLOAD_ENABLED",
        _bool_from_env(data.get("CANDIDATE_FILE_UPLOAD_ENABLED"), False),
    )
    updates["CANDIDATE_FILE_UPLOAD_ENABLED"] = str(uploads_enabled).lower()
    updates["FILESPACE_UPLOAD_MAX_MB"] = _upload_limit(data.get("FILESPACE_UPLOAD_MAX_MB"))

    env_path.write_text(_update_env_text(text, updates), encoding="utf-8")
    print(f"Saved setup to {env_path}")
    print("")
    return updates

