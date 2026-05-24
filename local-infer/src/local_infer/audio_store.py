from __future__ import annotations

import base64
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import RLock


@dataclass(frozen=True)
class AudioChunk:
    session_id: str
    timestamp_ms: int
    audio_wav_base64: str
    duration_ms: int

    @property
    def end_timestamp_ms(self) -> int:
        return self.timestamp_ms + self.duration_ms

    @property
    def wav_bytes(self) -> bytes:
        return base64.b64decode(self.audio_wav_base64, validate=True)


class AudioStore:
    """Bounded in-memory per-session WAV chunk buffer."""

    def __init__(self, max_chunks_per_session: int = 20) -> None:
        if max_chunks_per_session < 1:
            raise ValueError("max_chunks_per_session must be >= 1")
        self.max_chunks_per_session = max_chunks_per_session
        self._chunks: dict[str, deque[AudioChunk]] = defaultdict(
            lambda: deque(maxlen=max_chunks_per_session)
        )
        self._lock = RLock()

    def add_chunk(
        self,
        session_id: str,
        timestamp_ms: int,
        audio_wav_base64: str,
        duration_ms: int,
    ) -> AudioChunk:
        if not session_id:
            raise ValueError("session_id is required")
        if not audio_wav_base64:
            raise ValueError("audio_wav_base64 is required")
        if duration_ms < 0:
            raise ValueError("duration_ms must be >= 0")
        base64.b64decode(audio_wav_base64, validate=True)
        chunk = AudioChunk(
            session_id=session_id,
            timestamp_ms=timestamp_ms,
            audio_wav_base64=audio_wav_base64,
            duration_ms=duration_ms,
        )
        with self._lock:
            self._chunks[session_id].append(chunk)
        return chunk

    def get_recent_chunks(self, session_id: str, limit: int | None = None) -> list[AudioChunk]:
        with self._lock:
            chunks = list(self._chunks.get(session_id, ()))
        if limit is None:
            return chunks
        if limit < 1:
            return []
        return chunks[-limit:]

    def get_window(self, session_id: str, window_ms: int) -> list[AudioChunk]:
        if window_ms < 1:
            return []
        chunks = self.get_recent_chunks(session_id)
        if not chunks:
            return []
        latest_end_ms = max(chunk.end_timestamp_ms for chunk in chunks)
        cutoff_ms = latest_end_ms - window_ms
        return [chunk for chunk in chunks if chunk.end_timestamp_ms > cutoff_ms]

    def total_duration_ms(self, session_id: str) -> int:
        return sum(chunk.duration_ms for chunk in self.get_recent_chunks(session_id))

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._chunks.pop(session_id, None)
