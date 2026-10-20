from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path


class PlaybackCache:
    def __init__(self, log):
        self.log = log
        self.ffmpeg = shutil.which("ffmpeg")
        self.cache_dir = Path(tempfile.gettempdir()) / "filespace-playback-cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def get_playable_video(self, source: Path) -> Path:
        """Create and reuse a browser-compatible MP4 for an MKV source."""
        try:
            stat = source.stat()
        except OSError:
            raise FileNotFoundError
        key = hashlib.sha256(
            f"{os.path.normcase(str(source))}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8")
        ).hexdigest()
        output = self.cache_dir / f"{key}.mp4"
        if output.is_file() and output.stat().st_size > 0:
            return output
        if not self.ffmpeg:
            raise RuntimeError("Browser playback requires FFmpeg. Install FFmpeg and restart FileSpace.")
        with self._locks_guard:
            lock = self._locks.setdefault(key, threading.Lock())
        with lock:
            if output.is_file() and output.stat().st_size > 0:
                return output
            temporary = output.with_suffix(".tmp.mp4")
            try:
                if temporary.exists():
                    temporary.unlink()
                self.log.write("-", "TRANSCODE_START", f"{source.name} -> browser MP4")
                result = subprocess.run(
                    [
                        self.ffmpeg, "-y", "-i", str(source), "-map", "0:v:0", "-map", "0:a:0?",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(temporary),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
                if result.returncode != 0 or not temporary.is_file() or temporary.stat().st_size == 0:
                    detail = (result.stderr or "FFmpeg did not produce an output file").strip()
                    raise RuntimeError(f"FFmpeg could not prepare this video: {detail[-500:]}")
                os.replace(temporary, output)
                self.log.write("-", "TRANSCODE_DONE", f"{source.name} ({output.stat().st_size} bytes)")
                return output
            finally:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass
                except OSError:
                    pass

