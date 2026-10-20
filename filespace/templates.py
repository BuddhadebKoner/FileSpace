from __future__ import annotations

import json
from importlib.resources import files

from .constants import SESSION_IDLE_SECONDS


def _template(name: str) -> str:
    return files("filespace.ui").joinpath(name).read_text(encoding="utf-8")


APP_PAGE = _template("app.html")
LOGIN_PAGE = _template("login.html")
QR_AUTH_PAGE = _template("qr_auth.html")


def upload_boot(cfg) -> dict:
    return {
        "enabled": cfg.candidate_file_upload_enabled,
        "max_bytes": cfg.upload_max_bytes,
        "extensions": list(cfg.upload_allowed_exts),
        "accept": [f".{ext}" for ext in cfg.upload_allowed_exts],
    }


def render_app_page(cfg, root_label: str) -> str:
    boot = "const BOOT=" + json.dumps({
        "root": root_label,
        "idle": SESSION_IDLE_SECONDS,
        "upload": upload_boot(cfg),
    }).replace("</", "<\\/") + ";"
    return APP_PAGE.replace("/*__BOOT__*/", boot)


def render_login_page(cfg) -> str:
    auth = json.dumps({
        "qr": cfg.qr_login_enabled,
        "password": cfg.password_login_enabled,
        "idle_minutes": max(1, SESSION_IDLE_SECONDS // 60),
    })
    return LOGIN_PAGE.replace("/*__AUTH__*/", auth)


def render_qr_auth_page() -> str:
    return QR_AUTH_PAGE

