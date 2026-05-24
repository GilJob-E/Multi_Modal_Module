from __future__ import annotations

import io
import math
import wave
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class AudioAnalysis:
    label: str
    confidence: float
    summary: str
    duration_ms: int
    sample_rate_hz: int
    channels: int
    active_ms: int
    longest_active_ms: int
    dominant_frequency_hz: float | None
    silence_detected: bool
    beep_tone_detected: bool
    vocal_cue_detected: bool

    def to_dict(self) -> dict[str, bool | float | int | str | None]:
        return asdict(self)


def analyze_wav_bytes(wav_bytes: bytes) -> AudioAnalysis:
    samples, sample_rate_hz, channels = _read_pcm16_mono(wav_bytes)
    duration_ms = round(len(samples) / sample_rate_hz * 1000) if sample_rate_hz else 0
    if not samples:
        return _analysis(
            label="silence/no-audio",
            confidence=1.0,
            summary="No decodable PCM samples were present in the WAV chunk.",
            duration_ms=0,
            sample_rate_hz=sample_rate_hz,
            channels=channels,
            active_ms=0,
            longest_active_ms=0,
            dominant_frequency_hz=None,
        )

    window_size = max(1, sample_rate_hz // 50)
    rms_windows = [_rms(samples[start : start + window_size]) for start in range(0, len(samples), window_size)]
    max_rms = max(rms_windows, default=0.0)
    active_threshold = max(250.0, max_rms * 0.2)
    active_windows = [index for index, rms in enumerate(rms_windows) if rms >= active_threshold]
    active_ms = round(len(active_windows) * window_size / sample_rate_hz * 1000)
    longest = _longest_consecutive_run(active_windows)

    if not longest or max_rms < 250.0:
        return _analysis(
            label="silence/no-audio",
            confidence=0.99,
            summary="No meaningful local audio energy was detected.",
            duration_ms=duration_ms,
            sample_rate_hz=sample_rate_hz,
            channels=channels,
            active_ms=0,
            longest_active_ms=0,
            dominant_frequency_hz=None,
        )

    segment_start = longest[0] * window_size
    segment_end = min(len(samples), (longest[-1] + 1) * window_size)
    active_segment = samples[segment_start:segment_end]
    longest_active_ms = round(len(active_segment) / sample_rate_hz * 1000)
    dominant_frequency_hz = _zero_crossing_frequency(active_segment, sample_rate_hz)

    if longest_active_ms >= 500 and 150.0 <= dominant_frequency_hz <= 650.0:
        return _analysis(
            label="vocal-cue/sustained-ah",
            confidence=0.86,
            summary=(
                "Detected a sustained mid-frequency ah-like vocal cue using local WAV analysis; "
                "this is degraded non-native audio analysis, not ASR."
            ),
            duration_ms=duration_ms,
            sample_rate_hz=sample_rate_hz,
            channels=channels,
            active_ms=active_ms,
            longest_active_ms=longest_active_ms,
            dominant_frequency_hz=round(dominant_frequency_hz, 1),
        )

    if dominant_frequency_hz >= 650.0 or longest_active_ms < 500:
        return _analysis(
            label="beep/tone",
            confidence=0.83,
            summary="Detected a deterministic tone/beep pattern rather than an ah-like vocal cue.",
            duration_ms=duration_ms,
            sample_rate_hz=sample_rate_hz,
            channels=channels,
            active_ms=active_ms,
            longest_active_ms=longest_active_ms,
            dominant_frequency_hz=round(dominant_frequency_hz, 1),
        )

    return _analysis(
        label="audio-present/unknown",
        confidence=0.55,
        summary="Detected local audio energy, but it did not match silence, beep, or sustained ah-like cue rules.",
        duration_ms=duration_ms,
        sample_rate_hz=sample_rate_hz,
        channels=channels,
        active_ms=active_ms,
        longest_active_ms=longest_active_ms,
        dominant_frequency_hz=round(dominant_frequency_hz, 1),
    )


def _read_pcm16_mono(wav_bytes: bytes) -> tuple[list[int], int, int]:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        sample_rate_hz = wav_file.getframerate()
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        frame_count = wav_file.getnframes()
        raw = wav_file.readframes(frame_count)
    if sample_width != 2:
        raise ValueError("only 16-bit PCM WAV audio is supported")
    if channels < 1:
        raise ValueError("WAV audio must have at least one channel")

    values = [int.from_bytes(raw[index : index + 2], "little", signed=True) for index in range(0, len(raw), 2)]
    if channels == 1:
        return values, sample_rate_hz, channels
    mono = []
    for index in range(0, len(values), channels):
        frame = values[index : index + channels]
        if frame:
            mono.append(round(sum(frame) / len(frame)))
    return mono, sample_rate_hz, channels


def _analysis(
    *,
    label: str,
    confidence: float,
    summary: str,
    duration_ms: int,
    sample_rate_hz: int,
    channels: int,
    active_ms: int,
    longest_active_ms: int,
    dominant_frequency_hz: float | None,
) -> AudioAnalysis:
    return AudioAnalysis(
        label=label,
        confidence=confidence,
        summary=summary,
        duration_ms=duration_ms,
        sample_rate_hz=sample_rate_hz,
        channels=channels,
        active_ms=active_ms,
        longest_active_ms=longest_active_ms,
        dominant_frequency_hz=dominant_frequency_hz,
        silence_detected=label == "silence/no-audio",
        beep_tone_detected=label == "beep/tone",
        vocal_cue_detected=label == "vocal-cue/sustained-ah",
    )


def _rms(samples: list[int]) -> float:
    if not samples:
        return 0.0
    return math.sqrt(sum(sample * sample for sample in samples) / len(samples))


def _longest_consecutive_run(values: list[int]) -> list[int]:
    best: list[int] = []
    current: list[int] = []
    for value in values:
        if current and value != current[-1] + 1:
            if len(current) > len(best):
                best = current
            current = []
        current.append(value)
    if len(current) > len(best):
        best = current
    return best


def _zero_crossing_frequency(samples: list[int], sample_rate_hz: int) -> float:
    signs = [1 if sample > 0 else -1 for sample in samples if sample != 0]
    if len(signs) < 2:
        return 0.0
    crossings = sum(1 for left, right in zip(signs, signs[1:]) if left != right)
    return crossings * sample_rate_hz / (2 * len(samples))
