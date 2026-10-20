from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from http.server import ThreadingHTTPServer
from pathlib import Path

from .activity import ActivityLog
from .auth import QrLoginStore, SessionStore, Throttle
from .constants import (
    SESSION_IDLE_SECONDS,
    TRUE_VALUES,
    UPLOAD_MAX_REQUESTS_PER_WINDOW,
    UPLOAD_QUOTA_BYTES,
    UPLOAD_QUOTA_WINDOW_SECONDS,
)
from .filetypes import fmt_bytes
from .playback import PlaybackCache
from .routes import ServerContext, make_handler
from .settings import ConfigStore, describe, ensure_env_file, parse_env
from .setup_wizard import can_prompt, run_setup_wizard
from .system import HAVE_QRCODE, browser_host, create_desktop_shortcut, local_ips, print_terminal_qr
from .thumbnails import ThumbCache
from .uploads import UploadRateLimiter


def launcher_path() -> Path:
    if sys.argv and sys.argv[0]:
        candidate = Path(sys.argv[0]).resolve()
        if candidate.name == "__main__.py" and candidate.parent.name == "filespace":
            repo_launcher = candidate.parents[1] / "fileserver.py"
            if repo_launcher.exists():
                return repo_launcher
        return candidate
    return Path(__file__).resolve().parents[1] / "fileserver.py"


def build_parser(default_env: Path, default_log: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start the FileSpace browser.")
    parser.add_argument(
        "--root",
        default=None,
        help="Root folder to share (default: FILESPACE_ROOT from .env, or D:\\)",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (0.0.0.0 allows other devices; default)")
    parser.add_argument("--port", type=int, default=6789, help="Port (default: 6789)")
    parser.add_argument("--env", default=str(default_env), help="Path to the settings file (default: .env next to fileserver.py)")
    parser.add_argument("--log", default=str(default_log), help="Activity log file (default: logs.txt next to fileserver.py)")
    parser.add_argument("--no-setup", action="store_true", help="Skip interactive .env setup prompts")
    return parser


def main(argv: list[str] | None = None) -> None:
    launcher = launcher_path()
    app_dir = launcher.parent
    parser = build_parser(app_dir / ".env", app_dir / "logs.txt")
    args = parser.parse_args(argv)

    env_path = Path(args.env).resolve()
    if not args.no_setup and can_prompt():
        run_setup_wizard(env_path, root_override=args.root)
    else:
        ensure_env_file(env_path)
    try:
        env_data = parse_env(env_path.read_text(encoding="utf-8-sig"))
    except OSError as e:
        raise SystemExit(f"Cannot read settings file {env_path}: {e}")

    root_value = args.root if args.root is not None else env_data.get("FILESPACE_ROOT", "D:\\")
    root = Path(root_value).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"Root directory does not exist: {root}")
    if env_data.get("FILESPACE_CREATE_SHORTCUT", "").strip().lower() in TRUE_VALUES:
        create_desktop_shortcut(launcher, env_path)

    log = ActivityLog(Path(args.log).resolve())
    qr_logins = QrLoginStore()

    def config_reloaded(cfg) -> None:
        qr_logins.clear()
        log.write("-", "CONFIG_RELOAD", f"{describe(cfg)}; pending QR login tokens cleared")

    store = ConfigStore(env_path, on_reload=config_reloaded)
    sessions = SessionStore(on_end=lambda ip, why: log.write(ip, "SESSION_END", why))
    throttle = Throttle()
    qr_throttle = Throttle()
    upload_rate = UploadRateLimiter(
        UPLOAD_MAX_REQUESTS_PER_WINDOW,
        UPLOAD_QUOTA_BYTES,
        UPLOAD_QUOTA_WINDOW_SECONDS,
    )

    package_dir = Path(__file__).resolve().parent
    old_log = log.path.with_name(log.path.stem + ".old" + log.path.suffix)
    excluded_files = {launcher, package_dir, env_path, log.path, old_log}
    excluded = set(excluded_files)
    if app_dir != root and app_dir not in root.parents:
        excluded.add(app_dir)
    excluded_norm = {os.path.normcase(str(p)) for p in excluded}

    ctx = ServerContext(
        root=root,
        root_label=root.name or str(root),
        env_path=env_path,
        log=log,
        store=store,
        sessions=sessions,
        qr_logins=qr_logins,
        throttle=throttle,
        qr_throttle=qr_throttle,
        upload_rate=upload_rate,
        thumbs=ThumbCache(),
        playback=PlaybackCache(log),
        excluded=excluded,
        excluded_norm=excluded_norm,
    )
    handler = make_handler(ctx)

    try:
        httpd = ThreadingHTTPServer((args.host, args.port), handler)
    except OSError as e:
        port_in_use = getattr(e, "winerror", None) == 10048 or getattr(e, "errno", None) in (48, 98, 10048)
        if port_in_use:
            raise SystemExit(
                f"\nFileSpace is already running or port {args.port} is busy.\n"
                f"Only one FileSpace server can use port {args.port} at a time.\n"
                f"Open http://127.0.0.1:{args.port}/ in your browser, stop the previous terminal, "
                "or start this one with a different --port.\n"
            )
        raise
    httpd.daemon_threads = True

    cfg = store.get()
    startup_qr_url, startup_qr_expires = None, None
    if cfg.qr_login_enabled:
        qr_token, startup_qr_expires = qr_logins.issue(cfg.fingerprint)
        startup_qr_url = f"{browser_host(args.host, args.port)}/auth/qr#t={qr_token}"

    log.write("-", "SERVER_START", f"port {args.port}, root {root}, {describe(cfg)}")
    line = "=" * 56
    print(line)
    print(" FileSpace is running")
    print(f" Shared root : {root}")
    print(f" Settings    : {env_path}")
    print(f" Activity log: {log.path}")
    print(" Not shared  : app files, .env, logs")
    print(f" Auto logout : after {SESSION_IDLE_SECONDS // 60} minutes of inactivity")
    print(f" Local URL   : http://127.0.0.1:{args.port}/")
    if args.host in ("0.0.0.0", ""):
        for ip in local_ips():
            print(f" Network URL : http://{ip}:{args.port}/")
    if startup_qr_url and startup_qr_expires:
        expires = datetime.fromtimestamp(startup_qr_expires).strftime("%H:%M:%S")
        print(f" QR login    : one-time code expires at {expires}")
        if print_terminal_qr(startup_qr_url):
            print(" QR status   : scan the code above with the browser/device you want to sign in")
        else:
            print(" QR package  : install qrcode to render the QR directly in this terminal")
            print(f" Login link  : {startup_qr_url}")
    if cfg.candidate_file_upload_enabled:
        print(f" Write mode  : authenticated users can create folders and upload files up to {fmt_bytes(cfg.upload_max_bytes)}")
    else:
        print(" Read-only   : folder creation, file changes, deletes, and uploads are disabled")
    print(f" Access      : {describe(cfg)}")
    if cfg.qr_login_enabled and not HAVE_QRCODE:
        print(" WARNING     : QR auth is enabled, but terminal QR rendering needs: pip install qrcode")
    if cfg.password_login_enabled and not cfg.credentials_ready:
        print(" WARNING     : password login is enabled but FILESPACE_EMAIL / FILESPACE_PASSWORD are not configured")
    if cfg.public:
        print(" WARNING     : PUBLIC mode - anyone who finds this address can attempt to log in")
    print(" Health check:")
    for check in ctx.run_health_checks(cfg):
        tag = {"ok": "OK  ", "warn": "WARN", "fail": "FAIL"}[check["status"]]
        print(f"   [{tag}] {check['name']}: {check['detail']}")
        if check["status"] != "ok":
            log.write("-", "HEALTH", f"{check['status'].upper()} {check['name']}: {check['detail']}")
    print(" Stop server : press Ctrl+C")
    print(" SECURITY    : plain HTTP is not encrypted; use a VPN or trusted networks")
    print(line, flush=True)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping FileSpace...")
    finally:
        log.write("-", "SERVER_STOP", "")
        httpd.server_close()

