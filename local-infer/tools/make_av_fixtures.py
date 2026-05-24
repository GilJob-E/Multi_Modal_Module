#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import struct
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any


SAMPLE_RATE = 16000
REQUIRED_PROBES = [
    "english_passphrase",
    "korean_passphrase",
    "no_audio_ablation",
    "beep_only",
    "av_sync",
    "cross_modal_event",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Create deterministic local AV probe fixtures.")
    parser.add_argument("--out", required=True, help="Output directory for fixtures and manifest.json")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg_path = shutil.which("ffmpeg")

    fixtures = {
        "english_passphrase": fixture_spec(
            key="english_passphrase",
            wav_name="english_passphrase.wav",
            video_name="english_passphrase.mp4",
            prompt=(
                "Listen to the explicit WAV audio. Return compact JSON with keys probe, heard, phrase, "
                "confidence. The expected phrase is not in this prompt; infer it from the audio."
            ),
            coded_text="native audio probe green",
            expected_substrings=["native", "audio", "probe", "green"],
            negative_substrings=["silent", "no audio", "beep only"],
            tones=[440, 554, 659, 880],
            visual_events=[(0, "blue"), (1200, "green"), (2400, "blue")],
            duration_ms=3200,
            role="audio_positive_english",
        ),
        "korean_passphrase": fixture_spec(
            key="korean_passphrase",
            wav_name="korean_passphrase.wav",
            video_name="korean_passphrase.mp4",
            prompt=(
                "Listen to the explicit WAV audio and answer in Korean JSON. Return keys probe, heard, phrase, "
                "confidence."
            ),
            coded_text="하늘 아",
            expected_substrings=["하늘", "아"],
            negative_substrings=["silent", "no audio", "beep only"],
            tones=[392, 494, 740],
            visual_events=[(0, "navy"), (1400, "cyan"), (2600, "navy")],
            duration_ms=3400,
            role="audio_positive_korean",
        ),
        "no_audio_ablation": fixture_spec(
            key="no_audio_ablation",
            wav_name="no_audio_ablation.wav",
            video_name="no_audio_ablation.mp4",
            prompt=(
                "The explicit WAV audio is the source of truth. Return compact JSON with keys probe, heard, "
                "audio_state."
            ),
            coded_text="",
            expected_substrings=["silent", "no audio"],
            negative_substrings=["native audio probe green", "하늘", "beep"],
            tones=[],
            visual_events=[(0, "blue"), (1200, "green"), (2400, "blue")],
            duration_ms=3200,
            role="no_audio_ablation",
        ),
        "beep_only": fixture_spec(
            key="beep_only",
            wav_name="beep_only.wav",
            video_name="beep_only.mp4",
            prompt=(
                "Classify the explicit WAV audio. Return compact JSON with keys probe, classification, speech. "
                "Do not transcribe non-speech tones as words."
            ),
            coded_text="beep beep",
            expected_substrings=["beep", "tone", "non-speech"],
            negative_substrings=["native audio probe green", "하늘"],
            tones=[1000, 1000, 1000],
            visual_events=[(0, "gray"), (700, "white"), (1400, "gray"), (2100, "white")],
            duration_ms=2800,
            role="non_speech_audio_control",
        ),
        "av_sync": fixture_spec(
            key="av_sync",
            wav_name="av_sync.wav",
            video_name="av_sync.mp4",
            prompt=(
                "Use the explicit WAV audio and muted video. Return compact JSON with keys probe, sync_events, "
                "alignment. Mention whether the tones align with visual flashes."
            ),
            coded_text="sync flash one two",
            expected_substrings=["sync", "align", "flash"],
            negative_substrings=["silent", "no audio"],
            tones=[660, 660],
            visual_events=[(0, "black"), (1000, "white"), (1300, "black"), (2200, "white"), (2500, "black")],
            duration_ms=3400,
            role="audio_video_sync",
            event_timing={
                "audio_beep_ms": [1000, 2200],
                "visual_flash_ms": [1000, 2200],
                "max_alignment_error_ms": 120,
            },
        ),
        "cross_modal_event": fixture_spec(
            key="cross_modal_event",
            wav_name="cross_modal_event.wav",
            video_name="cross_modal_event.mp4",
            prompt=(
                "Detect the combined event in the muted video plus explicit WAV audio. The target is a sky-look "
                "visual cue concurrent with an ah-like vocal tone. Return compact JSON with keys probe, "
                "cross_modal_event, event_time_ms, response."
            ),
            coded_text="sky look plus ah tone",
            expected_substrings=["sky", "look", "ah", "event"],
            negative_substrings=["silent", "no audio", "audio only"],
            tones=[],
            tone_events=[{"start_ms": 1700, "duration_ms": 900, "frequency_hz": 440, "amplitude": 0.35}],
            visual_events=[(0, "gray"), (1600, "sky"), (2600, "gray")],
            duration_ms=4200,
            role="cross_modal_event",
            event_timing={
                "target_event_start_ms": 1600,
                "target_event_end_ms": 2600,
                "audio_cue_ms": 1700,
                "visual_cue_ms": 1600,
                "response_budget_ms": 2000,
            },
        ),
    }

    for key in REQUIRED_PROBES:
        spec = fixtures[key]
        write_wav(out_dir / spec["audio_file"], spec["tone_plan"], spec["duration_ms"])
        write_video(out_dir / spec["video_file"], spec["visual_events"], spec["duration_ms"], ffmpeg_path)
        spec["files"] = file_records(out_dir, [spec["audio_file"], spec["video_file"]])

    manifest = {
        "schema_version": 1,
        "created_by": "local-infer/tools/make_av_fixtures.py",
        "deterministic": True,
        "local_only": True,
        "sample_rate_hz": SAMPLE_RATE,
        "required_probes": REQUIRED_PROBES,
        "limitations": [
            "No hosted TTS or ASR is used.",
            "Speech passphrase fixtures are deterministic tone-coded WAV controls, not human-spoken recordings.",
            "Model success must be interpreted as native explicit-audio ingestion plus expected semantic mapping, not human speech transcription quality.",
        ],
        "fixtures": fixtures,
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(manifest_path), "fixtures": REQUIRED_PROBES}, ensure_ascii=False))


def fixture_spec(
    *,
    key: str,
    wav_name: str,
    video_name: str,
    prompt: str,
    coded_text: str,
    expected_substrings: list[str],
    negative_substrings: list[str],
    tones: list[int],
    tone_events: list[dict[str, Any]] | None = None,
    visual_events: list[tuple[int, str]],
    duration_ms: int,
    role: str,
    event_timing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "role": role,
        "audio_file": wav_name,
        "audio_mime_type": "audio/wav",
        "audio_transport": "input_audio_base64_wav",
        "video_file": video_name,
        "video_mime_type": "video/mp4",
        "video_audio_policy": "muted_video_track_only; audio is supplied explicitly as WAV",
        "duration_ms": duration_ms,
        "prompt": prompt,
        "expected_answer": {
            "coded_text": coded_text,
            "expected_substrings": expected_substrings,
            "negative_substrings": negative_substrings,
            "machine_check": "casefold_substring_match",
        },
        "tone_plan": tone_events if tone_events is not None else tone_plan(tones, duration_ms),
        "visual_events": [{"time_ms": time_ms, "cue": cue} for time_ms, cue in visual_events],
        "event_timing": event_timing or {},
    }


def tone_plan(tones: list[int], duration_ms: int) -> list[dict[str, Any]]:
    if not tones:
        return []
    gap_ms = 220
    tone_ms = 360
    usable_ms = len(tones) * tone_ms + max(0, len(tones) - 1) * gap_ms
    start_ms = max(250, (duration_ms - usable_ms) // 2)
    plan = []
    for index, freq_hz in enumerate(tones):
        plan.append(
            {
                "index": index,
                "start_ms": start_ms + index * (tone_ms + gap_ms),
                "duration_ms": tone_ms,
                "frequency_hz": freq_hz,
                "amplitude": 0.35,
            }
        )
    return plan


def write_wav(path: Path, plan: list[dict[str, Any]], duration_ms: int) -> None:
    total_samples = int(SAMPLE_RATE * duration_ms / 1000)
    samples = [0.0] * total_samples
    for tone in plan:
        start = int(SAMPLE_RATE * tone["start_ms"] / 1000)
        count = int(SAMPLE_RATE * tone["duration_ms"] / 1000)
        freq = float(tone["frequency_hz"])
        amplitude = float(tone["amplitude"])
        for offset in range(count):
            sample_index = start + offset
            if sample_index >= total_samples:
                break
            fade = min(1.0, offset / 160, (count - offset) / 160)
            samples[sample_index] += amplitude * fade * math.sin(2 * math.pi * freq * sample_index / SAMPLE_RATE)

    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        for sample in samples:
            clamped = max(-0.95, min(0.95, sample))
            wav_file.writeframesraw(struct.pack("<h", int(clamped * 32767)))


def write_video(path: Path, visual_events: list[dict[str, Any]], duration_ms: int, ffmpeg_path: str | None) -> None:
    if ffmpeg_path is None:
        path.write_bytes(b"ffmpeg unavailable; muted video fixture not generated\n")
        return
    fps = 4
    frame_count = max(1, math.ceil(duration_ms / 1000 * fps))
    with tempfile.TemporaryDirectory() as tmp:
        frame_dir = Path(tmp)
        for frame_index in range(frame_count):
            time_ms = int(frame_index * 1000 / fps)
            cue = cue_at(visual_events, time_ms)
            write_ppm(frame_dir / f"frame_{frame_index:04d}.ppm", color_for_cue(cue))
        command = [
            ffmpeg_path,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(frame_dir / "frame_%04d.ppm"),
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(path),
        ]
        subprocess.run(command, check=True)


def cue_at(events: list[dict[str, Any]], time_ms: int) -> str:
    active = events[0]["cue"]
    for event in events:
        if time_ms >= int(event["time_ms"]):
            active = str(event["cue"])
    return active


def color_for_cue(cue: str) -> tuple[int, int, int]:
    return {
        "black": (0, 0, 0),
        "blue": (24, 80, 180),
        "cyan": (40, 190, 210),
        "gray": (110, 110, 110),
        "green": (40, 170, 70),
        "navy": (12, 30, 80),
        "sky": (100, 170, 240),
        "white": (245, 245, 245),
    }.get(cue, (120, 120, 120))


def write_ppm(path: Path, color: tuple[int, int, int]) -> None:
    width = 96
    height = 72
    header = f"P6\n{width} {height}\n255\n".encode("ascii")
    pixel = bytes(color)
    path.write_bytes(header + pixel * width * height)


def file_records(out_dir: Path, names: list[str]) -> dict[str, dict[str, Any]]:
    records = {}
    for name in names:
        path = out_dir / name
        data = path.read_bytes()
        records[name] = {
            "path": name,
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    return records


if __name__ == "__main__":
    main()
