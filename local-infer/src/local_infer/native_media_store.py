from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from threading import RLock


_SAFE_SESSION_ID = re.compile(r"^[A-Za-z0-9_-]+$")
_NATIVE_MP4_MIME_TYPE = "video/mp4"
_MAX_WINDOW_DURATION_MS = 30_000


@dataclass(frozen=True)
class NativeMediaWindow:
    session_id: str
    start_ms: int
    end_ms: int
    duration_ms: int
    mime_type: str
    sha256: str
    host_path: str
    file_url: str
    size_bytes: int


class NativeMediaStore:
    """Bounded file-backed per-session MP4 window buffer."""

    def __init__(
        self,
        runtime_dir: str | Path,
        url_prefix: str,
        max_windows_per_session: int = 6,
        max_total_bytes: int = 200 * 1024 * 1024,
        max_window_bytes: int = 25 * 1024 * 1024,
    ) -> None:
        if max_windows_per_session < 1:
            raise ValueError("max_windows_per_session must be >= 1")
        if max_total_bytes < 1:
            raise ValueError("max_total_bytes must be >= 1")
        if max_window_bytes < 1:
            raise ValueError("max_window_bytes must be >= 1")
        self.runtime_dir = Path(runtime_dir)
        self.url_prefix = url_prefix.rstrip("/")
        self.max_windows_per_session = max_windows_per_session
        self.max_total_bytes = max_total_bytes
        self.max_window_bytes = max_window_bytes
        self._windows: dict[str, deque[NativeMediaWindow]] = defaultdict(deque)
        self._lock = RLock()
        self._total_bytes = 0
        self._sequence = 0

    def add_window(
        self,
        session_id: str,
        start_ms: int,
        end_ms: int,
        video_mp4_base64: str,
        mime_type: str = _NATIVE_MP4_MIME_TYPE,
    ) -> NativeMediaWindow:
        self._validate_session_id(session_id)
        if mime_type != _NATIVE_MP4_MIME_TYPE:
            raise ValueError("mime_type must be video/mp4")
        if end_ms <= start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        duration_ms = end_ms - start_ms
        if duration_ms > _MAX_WINDOW_DURATION_MS:
            raise ValueError("duration_ms must be <= 30000")
        try:
            media_bytes = base64.b64decode(video_mp4_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("video_mp4_base64 must be valid base64") from exc
        if not media_bytes:
            raise ValueError("decoded video bytes are required")
        size_bytes = len(media_bytes)
        if size_bytes > self.max_window_bytes:
            raise ValueError("decoded video bytes exceed max_window_bytes")
        if size_bytes > self.max_total_bytes:
            raise ValueError("decoded video bytes exceed max_total_bytes")

        digest = hashlib.sha256(media_bytes).hexdigest()

        with self._lock:
            self._sequence += 1
            filename = f"{start_ms}-{end_ms}-{digest}-{self._sequence}.mp4"
            host_path = self.runtime_dir / session_id / filename
            file_url = f"{self.url_prefix}/{session_id}/{filename}"
            window = NativeMediaWindow(
                session_id=session_id,
                start_ms=start_ms,
                end_ms=end_ms,
                duration_ms=duration_ms,
                mime_type=mime_type,
                sha256=digest,
                host_path=str(host_path),
                file_url=file_url,
                size_bytes=size_bytes,
            )
            host_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = host_path.with_suffix(".tmp")
            temp_path.write_bytes(media_bytes)
            os.replace(temp_path, host_path)
            session_windows = self._windows[session_id]
            session_windows.append(window)
            self._total_bytes += size_bytes
            self._evict_session_overflow(session_windows)
            self._evict_total_overflow()
        return window

    def get_recent_windows(
        self, session_id: str, limit: int | None = None
    ) -> list[NativeMediaWindow]:
        with self._lock:
            windows = list(self._windows.get(session_id, ()))
        if limit is None:
            return windows
        if limit < 1:
            return []
        return windows[-limit:]

    def latest(self, session_id: str) -> NativeMediaWindow | None:
        recent = self.get_recent_windows(session_id, limit=1)
        if not recent:
            return None
        return recent[0]

    def total_bytes(self) -> int:
        with self._lock:
            return self._total_bytes

    def clear(self, session_id: str) -> None:
        with self._lock:
            windows = list(self._windows.pop(session_id, ()))
            for window in windows:
                self._delete_window_file(window)

    def _evict_session_overflow(self, session_windows: deque[NativeMediaWindow]) -> None:
        while len(session_windows) > self.max_windows_per_session:
            self._delete_window_file(session_windows.popleft())

    def _evict_total_overflow(self) -> None:
        while self._total_bytes > self.max_total_bytes:
            oldest = self._pop_oldest_window()
            if oldest is None:
                break
            self._delete_window_file(oldest)

    def _pop_oldest_window(self) -> NativeMediaWindow | None:
        oldest_session_id: str | None = None
        oldest_window: NativeMediaWindow | None = None
        for session_id, windows in self._windows.items():
            if windows and (oldest_window is None or windows[0].end_ms < oldest_window.end_ms):
                oldest_session_id = session_id
                oldest_window = windows[0]
        if oldest_session_id is None or oldest_window is None:
            return None
        windows = self._windows[oldest_session_id]
        removed = windows.popleft()
        if not windows:
            self._windows.pop(oldest_session_id, None)
        return removed

    def _delete_window_file(self, window: NativeMediaWindow) -> None:
        try:
            Path(window.host_path).unlink()
        except FileNotFoundError:
            pass
        self._total_bytes = max(0, self._total_bytes - window.size_bytes)

    @staticmethod
    def _validate_session_id(session_id: str) -> None:
        if not session_id:
            raise ValueError("session_id is required")
        if not _SAFE_SESSION_ID.fullmatch(session_id):
            raise ValueError("session_id must contain only letters, numbers, underscore, or dash")
