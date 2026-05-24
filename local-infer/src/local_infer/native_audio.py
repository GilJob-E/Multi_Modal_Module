from __future__ import annotations

import base64
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class NativeInputAudio:
    data: str
    format: str = "wav"

    @classmethod
    def from_wav_bytes(cls, wav_bytes: bytes) -> "NativeInputAudio":
        if not wav_bytes:
            raise ValueError("native audio output is empty")
        return cls(data=base64.b64encode(wav_bytes).decode("ascii"))

    def to_content_part(self) -> dict[str, object]:
        return {"type": "input_audio", "input_audio": {"data": self.data, "format": self.format}}


@dataclass(frozen=True)
class NativeAudioExtractor:
    ffmpeg_binary: str = "ffmpeg"
    timeout_seconds: float = 10.0
    max_audio_seconds: float = 30.0

    def extract_window(self, source_mp4_path: str | Path, *, start_seconds: float, duration_seconds: float) -> NativeInputAudio:
        if duration_seconds <= 0:
            raise ValueError("native audio duration must be positive")
        if duration_seconds > self.max_audio_seconds:
            raise ValueError(f"native audio duration exceeds {self.max_audio_seconds:g}s")

        command = [
            self.ffmpeg_binary,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            _format_seconds(start_seconds),
            "-t",
            _format_seconds(duration_seconds),
            "-i",
            str(source_mp4_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-acodec",
            "pcm_s16le",
            "-f",
            "wav",
            "pipe:1",
        ]

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                check=False,
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise ValueError(f"ffmpeg binary not found: {self.ffmpeg_binary}") from exc
        except subprocess.TimeoutExpired as exc:
            raise ValueError(f"ffmpeg timed out after {self.timeout_seconds:g}s") from exc

        if completed.returncode != 0:
            stderr = completed.stderr.decode("utf-8", errors="replace").strip()
            detail = f": {stderr}" if stderr else ""
            raise ValueError(f"ffmpeg failed with exit code {completed.returncode}{detail}")
        if not completed.stdout:
            raise ValueError("native audio output is empty")

        return NativeInputAudio.from_wav_bytes(completed.stdout)


def _format_seconds(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")
