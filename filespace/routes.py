from __future__ import annotations

import hmac
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import shutil
import time
from collections import deque
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from .activity import ActivityLog
from .auth import QrLoginStore, SessionStore, Throttle
from .constants import (
    CHUNK,
    COOKIE_NAME,
    CSP,
    INLINE_SVG_CSP,
    SEARCH_MAX_RESULTS,
    SEARCH_MAX_SCANNED,
    SESSION_IDLE_SECONDS,
    SESSION_MAX_SECONDS,
    START_TIME,
    UPLOAD_BODY_OVERHEAD,
)
from .filetypes import PREVIEW, THUMB_EXTS, file_ext, fmt_bytes, kind_of
from .fs_utils import fmt_path, hidden_attr, skip_name
from .playback import PlaybackCache
from .settings import ConfigStore, Settings
from .system import HAVE_QRCODE
from .templates import render_app_page, render_login_page, render_qr_auth_page, upload_boot
from .thumbnails import HAVE_PIL, ThumbCache
from .uploads import (
    UploadRateLimiter,
    safe_upload_filename,
    validate_folder_name,
    validate_upload_file,
)


@dataclass
class ServerContext:
    root: Path
    root_label: str
    env_path: Path
    log: ActivityLog
    store: ConfigStore
    sessions: SessionStore
    qr_logins: QrLoginStore
    throttle: Throttle
    qr_throttle: Throttle
    upload_rate: UploadRateLimiter
    thumbs: ThumbCache
    playback: PlaybackCache
    excluded: set[Path]
    excluded_norm: set[str]

    def is_excluded(self, path_str) -> bool:
        normalized = os.path.normcase(os.path.abspath(str(path_str)))
        return any(normalized == ex or normalized.startswith(ex + os.sep) for ex in self.excluded_norm)

    def resolve(self, rel: str) -> Path:
        parts = [p for p in rel.split("/") if p]
        for part in parts:
            if part in (".", "..") or ":" in part or part.endswith((".", " ")) or skip_name(part):
                raise PermissionError("Access denied")
        target = self.root.joinpath(*parts).resolve()
        try:
            target.relative_to(self.root)
        except ValueError:
            raise PermissionError("Access denied")
        if self.is_excluded(target):
            raise PermissionError("Access denied")
        if not target.exists():
            raise FileNotFoundError("Not found")
        return target

    def make_entry(self, name: str, rel: str, is_dir: bool, st: os.stat_result) -> dict:
        return {
            "name": name,
            "is_dir": is_dir,
            "relative_path": f"{rel}/{name}" if rel else name,
            "extension": "" if is_dir else os.path.splitext(name)[1].lstrip(".").upper(),
            "type": "Folder" if is_dir else (mimetypes.guess_type(name)[0] or "File"),
            "kind": "folder" if is_dir else kind_of(name),
            "modified": st.st_mtime,
            "size": None if is_dir else st.st_size,
        }

    def run_health_checks(self, cfg: Settings) -> list:
        out = []

        def add(name, status, detail):
            out.append({"name": name, "status": status, "detail": detail})

        try:
            with os.scandir(self.root) as it:
                next(it, None)
            add("Shared folder", "ok", "Readable")
        except OSError as e:
            add("Shared folder", "fail", f"Cannot read it ({e.strerror or e})")
        try:
            free = shutil.disk_usage(self.root).free
            add("Disk space", "ok" if free > (1 << 30) else "warn", f"{fmt_bytes(free)} free")
        except OSError:
            add("Disk space", "warn", "Could not be checked")
        try:
            with open(self.log.path, "a", encoding="utf-8"):
                pass
            add("Activity log", "ok", "Writable")
        except OSError:
            add("Activity log", "fail", "logs.txt is not writable")
        if self.env_path.is_file():
            add("Settings file", "ok", ".env loaded")
        else:
            add("Settings file", "fail", ".env is missing")

        login_status, details = "ok", []
        if cfg.qr_login_enabled:
            if HAVE_QRCODE:
                details.append(f"QR enabled - {self.qr_logins.count()} pending code(s)")
            else:
                login_status = "warn"
                details.append("QR enabled; install qrcode for terminal QR rendering")
        if cfg.password_login_enabled:
            if not cfg.credentials_ready:
                login_status = "fail"
                details.append("password login enabled but credentials are not configured")
            elif len(cfg.password) < 8:
                if login_status != "fail":
                    login_status = "warn"
                details.append("password fallback configured but short")
            else:
                details.append("password fallback configured")
        if not details:
            login_status, details = "fail", ["no authentication method enabled"]
        details.append(f"{self.sessions.count()} active session(s)")
        add("Login", login_status, "; ".join(details))

        if cfg.public:
            add("Access", "warn", "Public: any device can reach the login page")
        else:
            count = len(cfg.networks)
            entry = "entry" if count == 1 else "entries"
            add("Access", "ok", f"Restricted to {count} allowed IP {entry} + this PC")

        if cfg.candidate_file_upload_enabled:
            try:
                probe = self.root / f".filespace-write-check-{secrets.token_hex(4)}.tmp"
                with open(probe, "xb"):
                    pass
                probe.unlink()
                upload_status, upload_detail = "ok", (
                    f"Enabled; max {fmt_bytes(cfg.upload_max_bytes)}; "
                    f"{len(cfg.upload_allowed_exts)} allowed type(s)"
                )
            except OSError:
                upload_status, upload_detail = "fail", "Enabled but shared folder is not writable"
        else:
            upload_status, upload_detail = "ok", "Disabled by CANDIDATE_FILE_UPLOAD_ENABLED=false"
        if cfg.upload_config_errors and upload_status != "fail":
            upload_status = "warn"
            upload_detail += "; " + "; ".join(cfg.upload_config_errors)
        add("Candidate writes", upload_status, upload_detail)

        if self.playback.ffmpeg:
            add("Browser video", "ok", "FFmpeg is available for MKV playback")
        else:
            add("Browser video", "warn", "Install FFmpeg to play MKV videos in the browser")
        add("App files", "ok", "FileSpace folder, .env and logs are hidden from sharing")
        add("Thumbnails", "ok", "Fast (Pillow)" if HAVE_PIL else "Basic (pip install pillow for faster thumbnails)")
        return out


def make_handler(ctx: ServerContext):
    class Handler(BaseHTTPRequestHandler):
        server_version = "FileSpace/2.0"

        def log_message(self, fmt, *args):
            print(f"[{self.log_date_time_string()}] {self.client_address[0]} - {fmt % args}")

        def _start(self, status, content_type, length=None, extra=None, csp=CSP, frame=False):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            if length is not None:
                self.send_header("Content-Length", str(length))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "SAMEORIGIN" if frame else "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")
            if csp:
                self.send_header("Content-Security-Policy", csp)
            for key, value in (extra or []):
                self.send_header(key, value)
            self.end_headers()

        def send_bytes(self, status, content, content_type="application/json; charset=utf-8", extra=None):
            self._start(status, content_type, len(content), extra)
            self.wfile.write(content)

        def send_json(self, status, obj, extra=None):
            self.send_bytes(status, json.dumps(obj).encode("utf-8"), extra=extra)

        def send_html(self, status, html):
            self.send_bytes(status, html.encode("utf-8"), "text/html; charset=utf-8")

        def read_json_body(self, max_length: int) -> dict:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                raise ValueError("Bad request.")
            if length <= 0 or length > max_length:
                raise ValueError("Bad request.")
            try:
                body = json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise ValueError("Bad request.")
            if not isinstance(body, dict):
                raise ValueError("Bad request.")
            return body

        def read_upload_file(self, cfg: Settings) -> tuple[str, str, bytes]:
            content_type = self.headers.get("Content-Type", "")
            if content_type.split(";", 1)[0].strip().lower() != "multipart/form-data":
                raise ValueError("Upload must be multipart/form-data.")
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                raise ValueError("Bad request.")
            if length <= 0:
                raise ValueError("Bad request.")
            if length > cfg.upload_max_bytes + UPLOAD_BODY_OVERHEAD:
                self.close_connection = True
                raise OverflowError(f"Upload is larger than {fmt_bytes(cfg.upload_max_bytes)}.")
            wait = ctx.upload_rate.check(self.client_ip(), length)
            if wait:
                self.close_connection = True
                raise RuntimeError(f"RATE_LIMIT:{wait}")
            raw = self.rfile.read(length)
            header = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8", "replace")
            msg = BytesParser(policy=policy.default).parsebytes(header + raw)
            if not msg.is_multipart():
                raise ValueError("Bad upload request.")
            files = []
            for part in msg.iter_parts():
                if part.get_content_disposition() != "form-data":
                    continue
                field_name = part.get_param("name", header="content-disposition")
                filename = part.get_filename()
                if field_name == "file" and filename:
                    payload = part.get_payload(decode=True)
                    if payload is None:
                        content = part.get_content()
                        payload = content.encode("utf-8") if isinstance(content, str) else bytes(content)
                    files.append((filename, part.get_content_type(), payload))
            if len(files) != 1:
                raise ValueError("Upload exactly one file.")
            return files[0]

        def client_ip(self) -> str:
            return self.client_address[0]

        def ip_allowed(self, cfg: Settings) -> bool:
            if cfg.public:
                return True
            try:
                ip = ipaddress.ip_address(self.client_ip())
            except ValueError:
                return False
            if ip.version == 6 and ip.ipv4_mapped:
                ip = ip.ipv4_mapped
            if ip.is_loopback:
                return True
            return any(ip in net for net in cfg.networks if net.version == ip.version)

        def session_token(self):
            raw = self.headers.get("Cookie")
            if not raw:
                return None
            try:
                jar = SimpleCookie()
                jar.load(raw)
            except Exception:
                return None
            morsel = jar.get(COOKIE_NAME)
            return morsel.value if morsel else None

        def session_cookie(self, token: str) -> str:
            return f"{COOKIE_NAME}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_MAX_SECONDS}"

        def expired_session_cookie(self) -> str:
            return f"{COOKIE_NAME}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"

        def authed(self, cfg: Settings, touch: bool = True) -> bool:
            token = self.session_token()
            return bool(token) and ctx.sessions.valid(token, cfg.fingerprint, touch)

        def deny(self):
            print(f"[blocked] {self.client_ip()} is not in FILESPACE_ALLOWED_IPS", flush=True)
            ctx.log.write(self.client_ip(), "BLOCKED_IP", f"{self.command} {self.path}")
            self.send_bytes(403, b"Access denied for this device.\n", "text/plain; charset=utf-8")

        def do_GET(self):
            cfg = ctx.store.get()
            if not self.ip_allowed(cfg):
                return self.deny()
            parsed = urlparse(self.path)
            route = parsed.path
            try:
                if route == "/healthz":
                    return self.api_healthz()
                if route == "/":
                    page = render_app_page(cfg, ctx.root_label) if self.authed(cfg) else render_login_page(cfg)
                    return self.send_html(200, page)
                if route == "/auth/qr":
                    if not cfg.qr_login_enabled:
                        return self.send_json(404, {"error": "Not found"})
                    return self.send_html(200, render_qr_auth_page())
                if route.startswith("/api/"):
                    if not self.authed(cfg, touch=(route != "/api/health")):
                        if route != "/api/health":
                            ctx.log.write(self.client_ip(), "UNAUTHORIZED", f"{route} without a valid session")
                        return self.send_json(401, {"error": "Please sign in."})
                    query = parse_qs(parsed.query)
                    rel = fmt_path(query.get("path", [""])[0])
                    if route == "/api/list":
                        return self.api_list(rel)
                    if route == "/api/search":
                        return self.api_search(rel, query.get("q", [""])[0].strip())
                    if route == "/api/download":
                        return self.api_download(rel)
                    if route == "/api/file":
                        return self.api_download(rel, inline=True)
                    if route == "/api/playback":
                        return self.api_playback(rel)
                    if route == "/api/thumb":
                        return self.api_thumb(rel)
                    if route == "/api/health":
                        return self.api_health(cfg)
                    if route == "/api/keepalive":
                        return self.send_json(200, {
                            "ok": True,
                            "idle_left": ctx.sessions.remaining(self.session_token()),
                            "idle_limit": SESSION_IDLE_SECONDS,
                        })
                self.send_json(404, {"error": "Not found"})
            except PermissionError as e:
                raw_path = parse_qs(parsed.query).get("path", [""])[0]
                ctx.log.write(self.client_ip(), "ACCESS_DENIED", f"{route} path={raw_path}")
                self.send_json(403, {"error": str(e) or "Access denied"})
            except FileNotFoundError:
                self.send_json(404, {"error": "Not found"})
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            except RuntimeError as e:
                print(f"[error] {self.path}: {e}", flush=True)
                try:
                    self.send_json(503, {"error": str(e)})
                except OSError:
                    pass
            except Exception as e:
                print(f"[error] {self.path}: {e!r}", flush=True)
                try:
                    self.send_json(500, {"error": "Server error"})
                except OSError:
                    pass

        def do_POST(self):
            cfg = ctx.store.get()
            if not self.ip_allowed(cfg):
                return self.deny()
            parsed = urlparse(self.path)
            route = parsed.path
            try:
                if route == "/auth/qr/consume":
                    return self.api_qr_consume(cfg)
                if route == "/login":
                    return self.api_login(cfg)
                if route == "/logout":
                    token = self.session_token()
                    if token:
                        ctx.sessions.destroy(token)
                    reason = parse_qs(parsed.query).get("reason", [""])[0]
                    detail = "signed out after inactivity" if reason == "idle" else ""
                    ctx.log.write(self.client_ip(), "LOGOUT", detail)
                    return self.send_json(200, {"ok": True}, extra=[("Set-Cookie", self.expired_session_cookie())])
                if route.startswith("/api/"):
                    if not self.authed(cfg):
                        ctx.log.write(self.client_ip(), "UNAUTHORIZED", f"{route} without a valid session")
                        return self.send_json(401, {"error": "Please sign in."})
                    if route in {"/api/upload", "/api/folder"} and not cfg.candidate_file_upload_enabled:
                        ctx.log.write(self.client_ip(), "WRITE_DISABLED", f"{route} blocked")
                        return self.send_json(403, {"error": "Candidate file uploads are disabled."})
                    query = parse_qs(parsed.query)
                    rel = fmt_path(query.get("path", [""])[0])
                    if route == "/api/upload":
                        return self.api_upload(rel, cfg)
                    if route == "/api/folder":
                        return self.api_create_folder(rel)
                self.send_json(404, {"error": "Not found"})
            except OverflowError as e:
                self.send_json(413, {"error": str(e) or "Upload is too large."})
            except ValueError as e:
                self.send_json(400, {"error": str(e) or "Bad request."})
            except PermissionError as e:
                raw_path = parse_qs(parsed.query).get("path", [""])[0]
                ctx.log.write(self.client_ip(), "ACCESS_DENIED", f"{route} path={raw_path}")
                self.send_json(403, {"error": str(e) or "Access denied"})
            except FileExistsError:
                self.send_json(409, {"error": "A folder with that name already exists."})
            except FileNotFoundError:
                self.send_json(404, {"error": "Not found"})
            except RuntimeError as e:
                message = str(e)
                if message.startswith("RATE_LIMIT:"):
                    wait = message.split(":", 1)[1] or "60"
                    return self.send_json(
                        429,
                        {"error": "Too many uploads. Try again later."},
                        extra=[("Retry-After", wait)],
                    )
                print(f"[error] {self.path}: {e}", flush=True)
                try:
                    self.send_json(503, {"error": "Upload is temporarily unavailable."})
                except OSError:
                    pass
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            except Exception as e:
                print(f"[error] {self.path}: {e!r}", flush=True)
                try:
                    self.send_json(500, {"error": "Server error"})
                except OSError:
                    pass

        def api_qr_consume(self, cfg: Settings):
            ip = self.client_ip()
            if not cfg.qr_login_enabled:
                ctx.log.write(ip, "QR_LOGIN_OFF", "QR login is disabled")
                return self.send_json(404, {"error": "QR login is disabled."})
            wait = ctx.qr_throttle.locked_for(ip)
            if wait:
                ctx.log.write(ip, "QR_LOGIN_LOCKED", f"attempt while locked out ({wait}s left)")
                return self.send_json(
                    429,
                    {"error": f"Too many attempts. Try again in {max(1, wait // 60)} minute(s)."},
                    extra=[("Retry-After", str(wait))],
                )
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if length <= 0 or length > 2048:
                    raise ValueError
                body = json.loads(self.rfile.read(length))
                token = str(body.get("token", "")).strip()
            except (ValueError, AttributeError, UnicodeDecodeError):
                return self.send_json(400, {"error": "Bad request."})
            ok, error = ctx.qr_logins.consume(token, cfg.fingerprint)
            if ok:
                ctx.qr_throttle.ok(ip)
                token = ctx.sessions.create(cfg.fingerprint, ip)
                ctx.qr_logins.clear()
                print(f"[qr-login] success from {ip}", flush=True)
                ctx.log.write(ip, "QR_LOGIN_OK", "")
                return self.send_json(200, {"ok": True}, extra=[("Set-Cookie", self.session_cookie(token))])
            time.sleep(0.4)
            locked = ctx.qr_throttle.fail(ip)
            print(f"[qr-login] FAILED from {ip}" + (" (now locked out)" if locked else ""), flush=True)
            detail = "invalid, expired, or already-used token" + (" -> IP locked out 15 min" if locked else "")
            ctx.log.write(ip, "QR_LOGIN_FAIL", detail)
            if locked:
                return self.send_json(
                    429,
                    {"error": f"Too many attempts. Try again in {locked // 60} minutes."},
                    extra=[("Retry-After", str(locked))],
                )
            return self.send_json(401, {"error": error})

        def api_login(self, cfg: Settings):
            ip = self.client_ip()
            if not cfg.password_login_enabled:
                ctx.log.write(ip, "LOGIN_OFF", "password login is disabled")
                return self.send_json(404, {"error": "Password login is disabled."})
            wait = ctx.throttle.locked_for(ip)
            if wait:
                ctx.log.write(ip, "LOGIN_LOCKED", f"attempt while locked out ({wait}s left)")
                return self.send_json(
                    429,
                    {"error": f"Too many attempts. Try again in {max(1, wait // 60)} minute(s)."},
                    extra=[("Retry-After", str(wait))],
                )
            if not cfg.credentials_ready:
                ctx.log.write(ip, "LOGIN_OFF", "credentials not configured in .env")
                return self.send_json(503, {"error": "Server login is not configured yet. Edit the .env file."})
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if length <= 0 or length > 4096:
                    raise ValueError
                body = json.loads(self.rfile.read(length))
                email, password = str(body.get("email", "")), str(body.get("password", ""))
            except (ValueError, AttributeError, UnicodeDecodeError):
                return self.send_json(400, {"error": "Bad request."})
            ok_email = hmac.compare_digest(email.strip().lower().encode("utf-8"), cfg.email.lower().encode("utf-8"))
            ok_pass = hmac.compare_digest(password.encode("utf-8"), cfg.password.encode("utf-8"))
            if ok_email and ok_pass:
                ctx.throttle.ok(ip)
                token = ctx.sessions.create(cfg.fingerprint, ip)
                print(f"[login] success from {ip}", flush=True)
                ctx.log.write(ip, "LOGIN_OK", f"email={email.strip()}")
                return self.send_json(200, {"ok": True}, extra=[("Set-Cookie", self.session_cookie(token))])
            time.sleep(0.6)
            locked = ctx.throttle.fail(ip)
            print(f"[login] FAILED from {ip}" + (" (now locked out)" if locked else ""), flush=True)
            ctx.log.write(ip, "LOGIN_FAIL", f"email={email.strip()}" + (" -> IP locked out 15 min" if locked else ""))
            if locked:
                return self.send_json(
                    429,
                    {"error": f"Too many attempts. Try again in {locked // 60} minutes."},
                    extra=[("Retry-After", str(locked))],
                )
            self.send_json(401, {"error": "Incorrect email or password."})

        def writable_folder(self, rel: str) -> Path:
            target = ctx.resolve(rel)
            if not target.is_dir():
                raise FileNotFoundError
            try:
                st = target.stat()
            except OSError:
                raise FileNotFoundError
            if hidden_attr(st):
                raise PermissionError("Access denied")
            return target

        def api_create_folder(self, rel: str):
            parent = self.writable_folder(rel)
            body = self.read_json_body(2048)
            name = validate_folder_name(str(body.get("name", "")))
            target = parent.joinpath(name).resolve()
            try:
                target.relative_to(ctx.root)
            except ValueError:
                raise PermissionError("Access denied")
            if ctx.is_excluded(target):
                raise PermissionError("Access denied")
            target.mkdir()
            st = target.stat()
            entry = ctx.make_entry(name, rel, True, st)
            ctx.log.write(self.client_ip(), "MKDIR", f"/{entry['relative_path']}")
            self.send_json(201, {"ok": True, "path": entry["relative_path"], "entry": entry})

        def api_upload(self, rel: str, cfg: Settings):
            parent = self.writable_folder(rel)
            filename, content_type, data = self.read_upload_file(cfg)
            try:
                ext = validate_upload_file(filename, content_type, data, cfg)
            except ValueError as e:
                if str(e).startswith("File is larger"):
                    raise OverflowError(str(e))
                raise
            safe_name = safe_upload_filename(filename, ext)
            final = parent.joinpath(safe_name).resolve()
            try:
                final.relative_to(ctx.root)
            except ValueError:
                raise PermissionError("Access denied")
            if ctx.is_excluded(final):
                raise PermissionError("Access denied")
            temp_name = f".{safe_name}.{secrets.token_hex(8)}.uploading"
            temporary = parent / temp_name
            try:
                with open(temporary, "xb") as fh:
                    fh.write(data)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(temporary, final)
            except OSError:
                try:
                    temporary.unlink()
                except OSError:
                    pass
                raise RuntimeError("Could not store the uploaded file.")
            st = final.stat()
            entry = ctx.make_entry(safe_name, rel, False, st)
            ctx.log.write(self.client_ip(), "UPLOAD", f"/{entry['relative_path']} ({len(data)} bytes)")
            self.send_json(201, {"ok": True, "path": rel, "filename": safe_name, "entry": entry})

        def api_list(self, rel: str):
            target = ctx.resolve(rel)
            if not target.is_dir():
                raise FileNotFoundError
            entries = []
            try:
                with os.scandir(target) as it:
                    for de in it:
                        if skip_name(de.name) or ctx.is_excluded(de.path):
                            continue
                        try:
                            st = de.stat()
                            is_dir = de.is_dir()
                        except OSError:
                            continue
                        if hidden_attr(st):
                            continue
                        entries.append(ctx.make_entry(de.name, rel, is_dir, st))
            except PermissionError:
                return self.send_json(403, {"error": "Windows denied access to this folder."})
            ctx.log.write(self.client_ip(), "LIST", f"/{rel} ({len(entries)} items)")
            self.send_json(200, {"path": rel, "entries": entries, "thumbs": HAVE_PIL})

        def api_search(self, rel: str, q: str):
            if len(q) < 2:
                return self.send_json(200, {"path": rel, "entries": [], "truncated": False})
            base = ctx.resolve(rel)
            if not base.is_dir():
                raise FileNotFoundError
            needle = q.lower()
            results, scanned, truncated = [], 0, False
            queue = deque([(base, rel)])
            while queue:
                folder, folder_rel = queue.popleft()
                try:
                    it = os.scandir(folder)
                except OSError:
                    continue
                with it:
                    for de in it:
                        if skip_name(de.name) or ctx.is_excluded(de.path):
                            continue
                        scanned += 1
                        if scanned > SEARCH_MAX_SCANNED or len(results) >= SEARCH_MAX_RESULTS:
                            truncated = True
                            queue.clear()
                            break
                        try:
                            st = de.stat()
                            is_dir = de.is_dir(follow_symlinks=False)
                        except OSError:
                            continue
                        if hidden_attr(st):
                            continue
                        if needle in de.name.lower():
                            results.append(ctx.make_entry(de.name, folder_rel, is_dir, st))
                        if is_dir:
                            child_rel = f"{folder_rel}/{de.name}" if folder_rel else de.name
                            queue.append((Path(de.path), child_rel))
            ctx.log.write(self.client_ip(), "SEARCH", f"q={q!r} in /{rel} ({len(results)} results)")
            self.send_json(200, {"path": rel, "entries": results, "truncated": truncated, "thumbs": HAVE_PIL})

        def api_thumb(self, rel: str):
            target = ctx.resolve(rel)
            if not target.is_file() or file_ext(target.name) not in THUMB_EXTS:
                raise FileNotFoundError
            st = target.stat()
            if hidden_attr(st):
                raise PermissionError("Access denied")
            data = ctx.thumbs.get(target, st)
            if not data:
                return self.send_json(404, {"error": "No thumbnail"})
            self.send_bytes(200, data, "image/jpeg")

        def api_health(self, cfg: Settings):
            checks = ctx.run_health_checks(cfg)
            order = {"ok": 0, "warn": 1, "fail": 2}
            overall = max((c["status"] for c in checks), key=lambda x: order[x], default="ok")
            self.send_json(200, {
                "status": overall,
                "uptime": int(time.time() - START_TIME),
                "idle_left": ctx.sessions.remaining(self.session_token()),
                "idle_limit": SESSION_IDLE_SECONDS,
                "checks": checks,
                "upload": upload_boot(cfg),
            })

        def api_healthz(self):
            """Public, minimal liveness probe; still limited by the IP allowlist."""
            try:
                with os.scandir(ctx.root) as it:
                    next(it, None)
                self.send_json(200, {"status": "ok"})
            except OSError:
                self.send_json(503, {"status": "fail"})

        def api_download(self, rel: str, inline: bool = False):
            target = ctx.resolve(rel)
            if not target.is_file():
                raise FileNotFoundError
            return self.serve_file(target, rel, inline)

        def api_playback(self, rel: str):
            target = ctx.resolve(rel)
            if not target.is_file():
                raise FileNotFoundError
            if kind_of(target.name) != "video" or file_ext(target.name) != "mkv":
                return self.api_download(rel, inline=True)
            playable = ctx.playback.get_playable_video(target)
            return self.serve_file(playable, rel + " [browser playback]", True, content_type="video/mp4")

        def serve_file(self, target: Path, rel: str, inline: bool = False, content_type: str | None = None):
            st = target.stat()
            if hidden_attr(st):
                raise PermissionError("Access denied")
            ctype, csp, disp = "application/octet-stream", CSP, "attachment"
            if inline:
                kind = kind_of(target.name)
                if kind not in ("image", "video", "audio", "pdf", "text"):
                    return self.send_json(415, {"error": "Preview is not available for this file type."})
                ctype = content_type or PREVIEW[file_ext(target.name)][1]
                disp = "inline"
                csp = INLINE_SVG_CSP if file_ext(target.name) == "svg" else None
            size = st.st_size
            start, end, status = 0, size - 1, 200
            range_header = self.headers.get("Range", "")
            if size > 0 and range_header.startswith("bytes=") and "," not in range_header:
                first, _, last = range_header[6:].partition("-")
                try:
                    if first == "":
                        start = max(size - int(last), 0)
                    else:
                        start = int(first)
                        end = int(last) if last else size - 1
                except ValueError:
                    start, end = 0, size - 1
                else:
                    if start > end or start >= size:
                        return self._start(416, "text/plain", 0, [("Content-Range", f"bytes */{size}")])
                    end = min(end, size - 1)
                    status = 206
            length = max(end - start + 1, 0)
            display_name = Path(rel).name
            ascii_name = re.sub(r'[^\x20-\x7e]|["\\;]', "_", display_name)
            extra = [
                ("Content-Disposition", f"{disp}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(display_name)}"),
                ("Accept-Ranges", "bytes"),
            ]
            if status == 206:
                extra.append(("Content-Range", f"bytes {start}-{end}/{size}"))
            self._start(status, ctype, length, extra, csp=csp, frame=inline)
            if not inline:
                detail = f"/{rel} ({length} of {size} bytes" + (f", range {start}-{end}" if status == 206 else "") + ")"
                ctx.log.write(self.client_ip(), "DOWNLOAD", detail)
            elif status == 200 or start == 0:
                ctx.log.write(self.client_ip(), "VIEW", f"/{rel} ({size} bytes)")
            try:
                with open(target, "rb") as fh:
                    fh.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = fh.read(min(CHUNK, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError):
                pass

    return Handler

