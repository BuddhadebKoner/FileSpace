from __future__ import annotations

import hashlib
import secrets
import threading
import time

from .constants import (
    LOGIN_LOCK_SECONDS,
    MAX_LOGIN_FAILURES,
    QR_TOKEN_SECONDS,
    SESSION_IDLE_SECONDS,
    SESSION_MAX_SECONDS,
)


class SessionStore:
    def __init__(self, on_end=None):
        self._d: dict[str, list] = {}
        self._lock = threading.Lock()
        self.on_end = on_end

    def _ended(self, ip: str, why: str) -> None:
        if self.on_end:
            self.on_end(ip, why)

    def create(self, fingerprint: str, ip: str = "-") -> str:
        token = secrets.token_urlsafe(32)
        now = time.time()
        expired = []
        with self._lock:
            for t, (_, created, last, sip) in list(self._d.items()):
                if now - last > SESSION_IDLE_SECONDS or now - created > SESSION_MAX_SECONDS:
                    expired.append(sip)
                    del self._d[t]
            self._d[token] = [fingerprint, now, now, ip]
        for sip in expired:
            self._ended(sip, "session expired")
        return token

    def valid(self, token: str, fingerprint: str, touch: bool = True) -> bool:
        now = time.time()
        why = None
        with self._lock:
            item = self._d.get(token)
            if not item:
                return False
            fp, created, last, ip = item
            if fp != fingerprint:
                why = "credentials changed in .env"
            elif now - last > SESSION_IDLE_SECONDS:
                why = f"inactive for {SESSION_IDLE_SECONDS // 60} minutes"
            elif now - created > SESSION_MAX_SECONDS:
                why = "maximum session length reached"
            if why:
                del self._d[token]
            elif touch:
                item[2] = now
        if why:
            self._ended(ip, "session ended: " + why)
            return False
        return True

    def remaining(self, token) -> int:
        with self._lock:
            item = self._d.get(token or "")
            if not item:
                return 0
            now = time.time()
            left = min(item[2] + SESSION_IDLE_SECONDS, item[1] + SESSION_MAX_SECONDS) - now
            return int(max(0, left))

    def destroy(self, token: str) -> None:
        with self._lock:
            self._d.pop(token, None)

    def count(self) -> int:
        with self._lock:
            return len(self._d)


class QrLoginStore:
    def __init__(self):
        self._d: dict[str, list] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _cleanup_locked(self, now: float) -> None:
        for key, (_, expires_at) in list(self._d.items()):
            if expires_at <= now:
                del self._d[key]

    def issue(self, fingerprint: str) -> tuple[str, float]:
        token = secrets.token_urlsafe(32)
        now = time.time()
        expires_at = now + QR_TOKEN_SECONDS
        with self._lock:
            self._cleanup_locked(now)
            self._d[self._digest(token)] = [fingerprint, expires_at]
        return token, expires_at

    def consume(self, token: str, fingerprint: str) -> tuple[bool, str]:
        if not token or len(token) > 256:
            return False, "QR code is invalid or has expired."
        digest = self._digest(token)
        now = time.time()
        with self._lock:
            self._cleanup_locked(now)
            item = self._d.pop(digest, None)
        if not item:
            return False, "QR code is invalid or has expired."
        if item[0] != fingerprint:
            return False, "Server authentication settings changed. Restart FileSpace for a fresh QR code."
        return True, ""

    def clear(self) -> None:
        with self._lock:
            self._d.clear()

    def count(self) -> int:
        now = time.time()
        with self._lock:
            self._cleanup_locked(now)
            return len(self._d)


class Throttle:
    def __init__(self):
        self._d: dict[str, list] = {}
        self._lock = threading.Lock()

    def locked_for(self, ip: str) -> int:
        with self._lock:
            item = self._d.get(ip)
            if not item:
                return 0
            remaining = int(item[1] - time.time())
            return remaining if remaining > 0 else 0

    def fail(self, ip: str) -> int:
        now = time.time()
        with self._lock:
            item = self._d.setdefault(ip, [0, 0.0, now])
            if now - item[2] > LOGIN_LOCK_SECONDS:
                item[0] = 0
            item[0] += 1
            item[2] = now
            if item[0] >= MAX_LOGIN_FAILURES:
                item[1] = now + LOGIN_LOCK_SECONDS
                item[0] = 0
                return LOGIN_LOCK_SECONDS
            return 0

    def ok(self, ip: str) -> None:
        with self._lock:
            self._d.pop(ip, None)

