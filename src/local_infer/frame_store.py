from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from threading import RLock


@dataclass(frozen=True)
class Frame:
    session_id: str
    timestamp_ms: int
    frame_jpeg_base64: str


class FrameStore:
    """Bounded in-memory per-session JPEG frame buffer.

    This is intentionally small and dependency-free. The gateway keeps recent
    frames only; long-term visual memory should be represented as summaries, not
    unbounded image accumulation.
    """

    def __init__(self, max_frames_per_session: int = 30) -> None:
        if max_frames_per_session < 1:
            raise ValueError("max_frames_per_session must be >= 1")
        self.max_frames_per_session = max_frames_per_session
        self._frames: dict[str, deque[Frame]] = defaultdict(
            lambda: deque(maxlen=max_frames_per_session)
        )
        self._lock = RLock()

    def add_frame(self, session_id: str, timestamp_ms: int, frame_jpeg_base64: str) -> Frame:
        if not session_id:
            raise ValueError("session_id is required")
        if not frame_jpeg_base64:
            raise ValueError("frame_jpeg_base64 is required")
        frame = Frame(
            session_id=session_id,
            timestamp_ms=timestamp_ms,
            frame_jpeg_base64=frame_jpeg_base64,
        )
        with self._lock:
            self._frames[session_id].append(frame)
        return frame

    def get_recent_frames(self, session_id: str, limit: int) -> list[Frame]:
        if limit < 1:
            return []
        with self._lock:
            frames = list(self._frames.get(session_id, ()))
        return frames[-limit:]

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._frames.pop(session_id, None)
