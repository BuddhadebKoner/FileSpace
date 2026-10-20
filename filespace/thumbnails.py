from __future__ import annotations

import io
import os
import threading
from collections import OrderedDict
from pathlib import Path


try:
    from PIL import Image, ImageOps
    HAVE_PIL = True
except Exception:  # pragma: no cover
    Image = None
    ImageOps = None
    HAVE_PIL = False


class ThumbCache:
    """Small in-memory cache of JPEG thumbnails. Pillow is optional."""

    def __init__(self, limit: int = 300):
        self.limit = limit
        self._d: OrderedDict = OrderedDict()
        self._lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(3)

    def get(self, path: Path, st: os.stat_result):
        if not HAVE_PIL:
            return None
        key = (str(path), st.st_mtime_ns, st.st_size)
        with self._lock:
            hit = self._d.get(key)
            if hit is not None:
                self._d.move_to_end(key)
                return hit
        with self._slots:
            data = self._make(path)
        if data:
            with self._lock:
                self._d[key] = data
                while len(self._d) > self.limit:
                    self._d.popitem(last=False)
        return data

    @staticmethod
    def _make(path: Path):
        try:
            assert Image is not None and ImageOps is not None
            with Image.open(path) as im:
                im = ImageOps.exif_transpose(im)
                im.thumbnail((360, 360))
                rgba = im.convert("RGBA")
                bg = Image.new("RGB", rgba.size, (24, 32, 52))
                bg.paste(rgba, mask=rgba.getchannel("A"))
                buf = io.BytesIO()
                bg.save(buf, "JPEG", quality=78)
                return buf.getvalue()
        except Exception:
            return None

