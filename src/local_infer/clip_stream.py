"""클립 파일 → GilJob식 입력(1fps JPEG 프레임 + 16kHz mono PCM) 추출.

테스트/시뮬레이션용 — 라이브 GilJob 탭이 줄 미디어(640×480 JPEG @1fps, 16kHz PCM Int16)를
로컬 클립으로 재현한다. 모듈 코어가 아니라 검증 입력 소스.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def extract_frames(clip: str | Path, *, start_s: float, dur_s: float, fps: float = 1.0) -> list[bytes]:
    """[start_s, start_s+dur_s) 구간을 fps로 샘플링한 JPEG 프레임 바이트 리스트."""
    with tempfile.TemporaryDirectory() as d:
        cmd = [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{start_s:.3f}", "-t", f"{dur_s:.3f}", "-i", str(clip),
            "-vf", f"fps={fps:g}", "-q:v", "3",
            str(Path(d, "f%05d.jpg")),
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=60)
        if r.returncode != 0:
            raise RuntimeError(f"frame extract failed: {r.stderr.decode('utf-8', 'replace')[:200]}")
        return [p.read_bytes() for p in sorted(Path(d).glob("f*.jpg"))]


def has_audio(clip: str | Path) -> bool:
    """클립에 오디오 스트림이 있는지."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=codec_type", "-of", "csv=p=0", str(clip)],
        capture_output=True, text=True, timeout=15,
    )
    return "audio" in r.stdout


def extract_pcm(clip: str | Path, *, start_s: float, dur_s: float, sample_rate: int = 16000) -> bytes:
    """[start_s, start_s+dur_s) 구간의 16kHz mono Int16 raw PCM 바이트.

    오디오 스트림이 없는 클립이면 b""를 반환한다(예외 대신).
    """
    if not has_audio(clip):
        return b""
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-ss", f"{start_s:.3f}", "-t", f"{dur_s:.3f}", "-i", str(clip),
        "-vn", "-ar", str(sample_rate), "-ac", "1", "-f", "s16le", "pipe:1",
    ]
    r = subprocess.run(cmd, capture_output=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"pcm extract failed: {r.stderr.decode('utf-8', 'replace')[:200]}")
    return r.stdout
