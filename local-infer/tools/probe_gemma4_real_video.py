#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOCKED_FILE_URL = "file:///workspace/gje/vid_0033.mp4"
LOCKED_CONTAINER_PATH = "/workspace/gje/vid_0033.mp4"
LOCKED_HOST_PATH = "/home/kio/workspace/gje/vid_0033.mp4"
LOCKED_SHA256 = "139e6b4cc725b0a4836baffde1e811b5cf41271e2a5ac0fa6f4dec41645cd4a8"
LOCKED_SOUNDTRACK_FILE_URL = "file:///workspace/gje/.sisyphus/evidence/vid0033-soundtrack.wav"
LOCKED_SOUNDTRACK_CONTAINER_PATH = "/workspace/gje/.sisyphus/evidence/vid0033-soundtrack.wav"
LOCKED_SOUNDTRACK_HOST_PATH = "/home/kio/workspace/gje/.sisyphus/evidence/vid0033-soundtrack.wav"
LOCKED_SOUNDTRACK_PROVENANCE_PATH = "/home/kio/workspace/gje/.sisyphus/evidence/vid0033-soundtrack-provenance.json"
ALLOWED_LOCAL_MEDIA_PATH = "/workspace/gje"
PROMPT_VERSION = "window_pack_native_v4"
LOCKED_WINDOW_PROVENANCE_PATH = "/home/kio/workspace/gje/.sisyphus/evidence/vid0033-window-provenance.json"
LOCKED_WINDOW_PACK_FILE_URL = "file:///workspace/gje/.sisyphus/evidence/vid0033-window-pack.wav"
LOCKED_WINDOW_PACK_CONTAINER_PATH = "/workspace/gje/.sisyphus/evidence/vid0033-window-pack.wav"
LOCKED_WINDOW_PACK_HOST_PATH = "/home/kio/workspace/gje/.sisyphus/evidence/vid0033-window-pack.wav"
LOCKED_WINDOW_PACK_PROVENANCE_PATH = "/home/kio/workspace/gje/.sisyphus/evidence/vid0033-window-pack-provenance.json"
LOCKED_WINDOW_AUDIO_PARTS = (
    {
        "window": "0_2s",
        "host_path": "/home/kio/workspace/gje/.sisyphus/evidence/vid0033-window-000000-002000.wav",
        "container_path": "/workspace/gje/.sisyphus/evidence/vid0033-window-000000-002000.wav",
        "url": "file:///workspace/gje/.sisyphus/evidence/vid0033-window-000000-002000.wav",
    },
    {
        "window": "12_17s",
        "host_path": "/home/kio/workspace/gje/.sisyphus/evidence/vid0033-window-012000-017000.wav",
        "container_path": "/workspace/gje/.sisyphus/evidence/vid0033-window-012000-017000.wav",
        "url": "file:///workspace/gje/.sisyphus/evidence/vid0033-window-012000-017000.wav",
    },
    {
        "window": "48_176_50_286s",
        "host_path": "/home/kio/workspace/gje/.sisyphus/evidence/vid0033-window-048176-050286.wav",
        "container_path": "/workspace/gje/.sisyphus/evidence/vid0033-window-048176-050286.wav",
        "url": "file:///workspace/gje/.sisyphus/evidence/vid0033-window-048176-050286.wav",
    },
)
REQUIRED_AUDIO_WINDOWS = tuple(part["window"] for part in LOCKED_WINDOW_AUDIO_PARTS)

LOCKED_STATUSES = {
    "serving_runtime_unresolved",
    "proof_invalid",
    "schema_media_failure",
    "gemma4_capability_no_go",
    "gemma4_native_real_video_pass",
}

FORBIDDEN_MARKERS = (
    "qwen",
    "generate-av-fallback",
    "/generate",
    "/v1/sessions/",
    "/frames",
    "/audio",
    "audio_analysis",
    "cross_modal_event",
    "sample30.mp4",
    "native_success=false",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def flatten_strings(value: Any) -> list[str]:
    strings: list[str] = []
    if isinstance(value, str):
        strings.append(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            strings.extend(flatten_strings(key))
            strings.extend(flatten_strings(item))
    elif isinstance(value, list):
        for item in value:
            strings.extend(flatten_strings(item))
    return strings


def forbidden_hits(value: Any) -> list[str]:
    flattened = "\n".join(flatten_strings(value)).lower()
    return [marker for marker in FORBIDDEN_MARKERS if marker in flattened]


def is_gemma4_model(model: str) -> bool:
    return model.startswith("google/gemma-4-")


def validate_ground_truth(ground_truth: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    if ground_truth.get("source_file_url") != LOCKED_FILE_URL:
        violations.append("ground_truth_source_file_url_mismatch")
    if ground_truth.get("source_container_path") != LOCKED_CONTAINER_PATH:
        violations.append("ground_truth_container_path_mismatch")
    if ground_truth.get("source_sha256") != LOCKED_SHA256:
        violations.append("ground_truth_sha256_mismatch")
    if ground_truth.get("diagnostic_only") is not True:
        violations.append("ground_truth_not_marked_diagnostic_only")
    if ground_truth.get("ground_truth_is_not_native_success") is not True:
        violations.append("ground_truth_success_guard_missing")
    return violations


def build_prompt(mode: str) -> str:
    if mode == "video_plus_window_pack_soundtrack":
        return (
            f"Prompt version: {PROMPT_VERSION}. Analyze the attached native media as one original MP4 plus "
            "one same-fixture window-pack WAV. The WAV is a direct chronological concatenation of three source "
            "audio windows from the same MP4: first 0.000-2.000 seconds, second 12.000-17.000 seconds, and "
            "third 48.176-50.286 seconds. Use the MP4 for visual context and the single WAV for native audio "
            "evidence. Do not use external tools, transcripts, prior fixture knowledge, or any supplied ground-truth "
            "answers. Do not invent exact spoken words unless they are clearly audible. Return only compact JSON with "
            "keys: visual_observations, audio_timeline, cross_modal_observations, uncertainty, "
            "do_not_transcribe_unless_clearly_audible. audio_timeline must include exactly these window keys: "
            "0_2s, 12_17s, 48_176_50_286s. For each window, provide classification and evidence. Choose the "
            "classification independently from the media as one of: speech, speech_like_activity, non_speech, "
            "quiet, silence, uncertain. These labels are options, not hints. For visual_observations, describe the "
            "visible person/scene and whether the speaker remains visible. For cross_modal_observations, tie visible "
            "speaker state to audio activity or non-activity in the same source time windows. If unsure, say uncertain."
        )
    if mode == "video_plus_windowed_soundtracks":
        return (
            f"Prompt version: {PROMPT_VERSION}. Analyze the attached native media as one original MP4 plus "
            "three separate same-fixture audio window WAVs in chronological order. Use the MP4 for visual context "
            "and the WAV parts for native audio evidence. Do not use external tools, transcripts, prior fixture "
            "knowledge, or any supplied ground-truth answers. Do not invent exact spoken words unless they are "
            "clearly audible. Return only compact JSON with keys: visual_observations, audio_timeline, "
            "cross_modal_observations, uncertainty, do_not_transcribe_unless_clearly_audible. "
            "audio_timeline must include exactly these window keys: 0_2s, 12_17s, 48_176_50_286s. For each "
            "window, provide classification and evidence. Choose the classification independently from the media as "
            "one of: speech, speech_like_activity, non_speech, quiet, silence, uncertain. These labels are options, "
            "not hints. For visual_observations, describe the visible person/scene and whether the speaker remains "
            "visible. For cross_modal_observations, tie visible speaker state to audio activity or non-activity in "
            "the same time windows. If a window is quiet or has no speech, say that explicitly. If unsure, say uncertain."
        )
    return (
        f"Prompt version: {PROMPT_VERSION}. Analyze the attached MP4 as native multimodal input, using both "
        "its visual track and audio track. Do not use external tools, transcripts, prior fixture knowledge, "
        "or any supplied ground-truth answers. Do not invent exact spoken words unless they are clearly audible. "
        "Return only compact JSON with keys: visual_observations, audio_timeline, cross_modal_observations, "
        "uncertainty, do_not_transcribe_unless_clearly_audible. "
        "audio_timeline must include exactly these window keys: 0_2s, 12_17s, 48_176_50_286s. For each window, "
        "provide classification and evidence. Choose the classification independently from the media as one of: "
        "speech, speech_like_activity, non_speech, quiet, silence, uncertain. These labels are options, not hints. "
        "For visual_observations, describe the visible person/scene and whether the speaker remains visible. "
        "For cross_modal_observations, tie visible speaker state to audio activity or non-activity in the same "
        "time windows. If a window is quiet or has no speech, say that explicitly. If unsure, say uncertain."
    )


def locked_window_audio_urls() -> list[str]:
    return [str(part["url"]) for part in LOCKED_WINDOW_AUDIO_PARTS]


def locked_window_pack_audio_url() -> str:
    return LOCKED_WINDOW_PACK_FILE_URL


def build_media_parts(video_url: str, mode: str, soundtrack_url: str | None) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = [
        {"type": "video_url", "video_url": {"url": video_url}},
    ]
    if mode == "video_plus_audio_from_same_fixture":
        parts.append({"type": "audio_url", "audio_url": {"url": soundtrack_url}})
    elif mode == "video_plus_windowed_soundtracks":
        parts.extend({"type": "audio_url", "audio_url": {"url": url}} for url in locked_window_audio_urls())
    elif mode == "video_plus_window_pack_soundtrack":
        parts.append({"type": "audio_url", "audio_url": {"url": locked_window_pack_audio_url()}})
    parts.append({"type": "text", "text": build_prompt(mode)})
    return parts


def build_payload(model: str, video_url: str, mode: str, soundtrack_url: str | None) -> dict[str, Any]:
    return {
        "model": model,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": build_media_parts(video_url, mode, soundtrack_url),
            }
        ],
        "max_tokens": 768,
        "temperature": 0,
    }


def media_part_trace(content: list[dict[str, Any]]) -> list[dict[str, Any]]:
    traced: list[dict[str, Any]] = []
    for part in content:
        part_type = part.get("type")
        if part_type == "video_url":
            traced.append({"type": "video_url", "url": part["video_url"]["url"]})
        elif part_type == "audio_url":
            traced.append({"type": "audio_url", "url": part["audio_url"]["url"], "source": "same_fixture_url"})
        elif part_type == "text":
            traced.append({"type": "text", "prompt_version": PROMPT_VERSION, "prompt_chars": len(part.get("text", ""))})
    return traced


def validate_soundtrack(mode: str, soundtrack_url: str | None) -> list[str]:
    violations: list[str] = []
    if mode == "video_plus_audio_from_same_fixture":
        if soundtrack_url != LOCKED_SOUNDTRACK_FILE_URL:
            violations.append("soundtrack_url_mismatch")
        if not Path(LOCKED_SOUNDTRACK_HOST_PATH).is_file():
            violations.append("soundtrack_host_file_missing")
    elif mode == "video_plus_windowed_soundtracks":
        if soundtrack_url is not None:
            violations.append("full_soundtrack_url_not_allowed_for_windowed_mode")
        for part in LOCKED_WINDOW_AUDIO_PARTS:
            if not Path(str(part["host_path"])).is_file():
                violations.append(f"window_audio_host_file_missing:{part['window']}")
            if "/audio" in str(part["host_path"]) or "/audio" in str(part["container_path"]) or "/audio" in str(part["url"]):
                violations.append(f"window_audio_forbidden_path:{part['window']}")
        if len(locked_window_audio_urls()) != 3:
            violations.append("window_audio_url_count_mismatch")
        if len(set(locked_window_audio_urls())) != 3:
            violations.append("window_audio_urls_not_unique")
        if not Path(LOCKED_WINDOW_PROVENANCE_PATH).is_file():
            violations.append("window_audio_provenance_missing")
    elif mode == "video_plus_window_pack_soundtrack":
        if soundtrack_url is not None:
            violations.append("full_soundtrack_url_not_allowed_for_window_pack_mode")
        if not Path(LOCKED_WINDOW_PACK_HOST_PATH).is_file():
            violations.append("window_pack_host_file_missing")
        if not Path(LOCKED_WINDOW_PACK_PROVENANCE_PATH).is_file():
            violations.append("window_pack_provenance_missing")
        checked_paths = (LOCKED_WINDOW_PACK_HOST_PATH, LOCKED_WINDOW_PACK_CONTAINER_PATH, LOCKED_WINDOW_PACK_FILE_URL)
        forbidden_path_terms = ("/audio", "audio_analysis", "cross_modal_event", "sample30", "quiet", "speech")
        for checked_path in checked_paths:
            for term in forbidden_path_terms:
                if term in checked_path:
                    violations.append(f"window_pack_forbidden_path:{term}")
    elif soundtrack_url is not None:
        violations.append("soundtrack_url_requires_video_plus_audio_mode")
    return violations


def load_soundtrack_provenance() -> dict[str, Any] | None:
    path = Path(LOCKED_SOUNDTRACK_PROVENANCE_PATH)
    if not path.is_file():
        return None
    try:
        data = load_json(path)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load_window_provenance() -> dict[str, Any] | None:
    path = Path(LOCKED_WINDOW_PROVENANCE_PATH)
    if not path.is_file():
        return None
    try:
        data = load_json(path)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load_window_pack_provenance() -> dict[str, Any] | None:
    path = Path(LOCKED_WINDOW_PACK_PROVENANCE_PATH)
    if not path.is_file():
        return None
    try:
        data = load_json(path)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def build_forbidden_path_checks(
    model: str,
    video_url: str,
    soundtrack_url: str | None,
    mode: str,
    ground_truth_violations: list[str],
) -> dict[str, Any]:
    violations = list(ground_truth_violations) + validate_soundtrack(mode, soundtrack_url)
    window_urls = locked_window_audio_urls() if mode == "video_plus_windowed_soundtracks" else []
    window_pack_url = locked_window_pack_audio_url() if mode == "video_plus_window_pack_soundtrack" else None
    if not is_gemma4_model(model):
        violations.append("non_gemma4_model")
    if video_url != LOCKED_FILE_URL:
        violations.append("wrong_fixture_url")
    marker_hits = forbidden_hits(
        {
            "model": model,
            "video_url": video_url,
            "soundtrack_url": soundtrack_url,
            "window_audio_urls": window_urls,
            "window_pack_url": window_pack_url,
        }
    )
    violations.extend(f"forbidden_marker:{marker}" for marker in marker_hits)
    checks: dict[str, Any] = {
        "status": "PASS" if not violations else "FAIL",
        "expected_file_url": LOCKED_FILE_URL,
        "actual_file_url": video_url,
        "expected_soundtrack_url": LOCKED_SOUNDTRACK_FILE_URL if mode == "video_plus_audio_from_same_fixture" else None,
        "actual_soundtrack_url": soundtrack_url,
        "expected_window_audio_urls": locked_window_audio_urls() if mode == "video_plus_windowed_soundtracks" else [],
        "actual_window_audio_urls": window_urls,
        "expected_window_pack_url": locked_window_pack_audio_url() if mode == "video_plus_window_pack_soundtrack" else None,
        "actual_window_pack_url": window_pack_url,
        "checked_marker_count": len(FORBIDDEN_MARKERS),
        "violations": sorted(set(violations)),
    }
    if violations:
        checks["checked_terms"] = list(FORBIDDEN_MARKERS)
    return checks


def build_request_trace(args: argparse.Namespace, payload: dict[str, Any], fixture_checks: dict[str, Any]) -> dict[str, Any]:
    content = payload["messages"][0]["content"]
    media_trace = media_part_trace(content)
    media_urls = [part["url"] for part in media_trace if "url" in part]
    fixture_identity: dict[str, Any] = {
        "host_path": LOCKED_HOST_PATH,
        "container_path": LOCKED_CONTAINER_PATH,
        "file_url": LOCKED_FILE_URL,
        "sha256": LOCKED_SHA256,
        "allowed_local_media_path": ALLOWED_LOCAL_MEDIA_PATH,
        "ground_truth_path": args.ground_truth,
    }
    trace: dict[str, Any] = {
        "endpoint": f"{args.base_url.rstrip('/')}/v1/chat/completions",
        "method": "POST",
        "model": args.model,
        "mode": args.mode,
        "video_url": args.video_url,
        "soundtrack_url": args.audio_url,
        "window_audio_urls": locked_window_audio_urls() if args.mode == "video_plus_windowed_soundtracks" else [],
        "window_pack_url": locked_window_pack_audio_url() if args.mode == "video_plus_window_pack_soundtrack" else None,
        "media_urls": media_urls,
        "media_content_parts": media_trace,
        "prompt_version": PROMPT_VERSION,
        "prompt_shape": {
            "response_format": "compact_json",
            "required_keys": [
                "visual_observations",
                "audio_timeline",
                "cross_modal_observations",
                "uncertainty",
                "do_not_transcribe_unless_clearly_audible",
            ],
            "audio_windows": list(REQUIRED_AUDIO_WINDOWS),
            "answer_leakage": "window labels only; expected classifications are not supplied",
        },
        "fixture_identity": fixture_identity,
        "forbidden_path_checks": fixture_checks,
        "request_body": payload,
    }
    if args.mode == "video_plus_audio_from_same_fixture":
        fixture_identity.update(
            {
                "soundtrack_host_path": LOCKED_SOUNDTRACK_HOST_PATH,
                "soundtrack_container_path": LOCKED_SOUNDTRACK_CONTAINER_PATH,
                "soundtrack_file_url": LOCKED_SOUNDTRACK_FILE_URL,
            }
        )
        trace["soundtrack_provenance"] = load_soundtrack_provenance()
    if args.mode == "video_plus_windowed_soundtracks":
        fixture_identity["window_audio_parts"] = list(LOCKED_WINDOW_AUDIO_PARTS)
        trace["window_provenance"] = load_window_provenance()
    if args.mode == "video_plus_window_pack_soundtrack":
        fixture_identity["window_pack_audio_part"] = {
            "host_path": LOCKED_WINDOW_PACK_HOST_PATH,
            "container_path": LOCKED_WINDOW_PACK_CONTAINER_PATH,
            "url": LOCKED_WINDOW_PACK_FILE_URL,
        }
        trace["window_pack_provenance"] = load_window_pack_provenance()
    return trace


def extract_answer(response: Any) -> str:
    if not isinstance(response, dict):
        return ""
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return ""
    message = first_choice.get("message", {})
    if not isinstance(message, dict):
        return ""
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(part.get("text", part)) for part in content if isinstance(part, dict))
    return str(content)


def contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def parse_answer_json(answer: str) -> Any:
    stripped = answer.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(stripped[start : end + 1])
        except json.JSONDecodeError:
            return None


def normalize_window_key(value: str) -> str:
    return value.lower().replace(" ", "").replace("-", "_").replace(".", "")


def timeline_window_text(parsed: Any, window: str) -> str:
    if not isinstance(parsed, dict):
        return ""
    timeline = parsed.get("audio_timeline")
    if not isinstance(timeline, dict):
        return ""
    wanted = normalize_window_key(window)
    for key, value in timeline.items():
        if normalize_window_key(str(key)) == wanted:
            return json.dumps(value, ensure_ascii=False).lower()
    return ""


def has_positive_speech(text: str) -> bool:
    positive_terms = (
        '"classification": "speech"',
        '"speech"',
        "clear speech",
        "speech_like_activity",
        "speech-like",
        "speech activity",
        "speaking",
        "talking",
        "voice",
        "vocal",
        "speaks",
        "spoken",
    )
    negative_terms = ("non_speech", "non-speech", "no speech", "no voice", "not speech", "without speech")
    return contains_any(text, positive_terms) and not contains_any(text, negative_terms)


def has_quiet_or_silence(text: str) -> bool:
    quiet_terms = (
        "quiet",
        "silence",
        "silent",
        "non_speech",
        "non-speech",
        "no speech",
        "no voice",
        "no audible",
        "low audio",
        "reduced audio",
        "audio drops",
        "audio fades",
        "activity disappears",
        "reduced activity",
        "little activity",
        "reduced sound",
        "stops speaking",
    )
    return contains_any(text, quiet_terms)


def evaluate_answer(answer: str, ground_truth: dict[str, Any]) -> tuple[str, str, str, dict[str, Any]]:
    parsed = parse_answer_json(answer)
    lowered = answer.lower()
    visual_groups = {
        "front_facing_person": ("person", "man", "speaker", "face", "front-facing", "camera"),
        "glasses_or_face_detail": ("glasses", "eyeglasses", "spectacles"),
        "indoor_plain_wall": ("indoor", "wall", "plain", "room"),
        "stable_framing": ("center", "centered", "still", "stable", "same position", "remains"),
    }
    audio_absence_terms = (
        "no discernible audio activity is present throughout",
        "no audio activity is present throughout",
        "no audio throughout",
        "silent throughout",
        "entire clip is silent",
        "there is no audio",
    )
    cross_groups = {
        "visual_speaker": visual_groups["front_facing_person"],
        "temporal_reference": ("0_2s", "12_17s", "48_176_50_286s", "48.176", "50.286", "beginning", "middle", "end", "window"),
        "modality_link": ("while", "as", "during", "with", "tie", "consistent", "same time", "concurrent"),
    }

    window_0_2_text = timeline_window_text(parsed, "0_2s")
    window_12_17_text = timeline_window_text(parsed, "12_17s")
    window_48_50_text = timeline_window_text(parsed, "48_176_50_286s")
    denies_audio_activity = contains_any(lowered, audio_absence_terms)
    visual_hits = {name: contains_any(lowered, terms) for name, terms in visual_groups.items()}
    window_0_2_speech = has_positive_speech(window_0_2_text)
    window_12_17_speech = has_positive_speech(window_12_17_text)
    speech_like_activity = window_0_2_speech or window_12_17_speech or has_positive_speech(lowered)
    quiet_or_silent_tail = has_quiet_or_silence(window_48_50_text)
    has_timeline_windows = all((window_0_2_text, window_12_17_text, window_48_50_text))
    audio_hits = {
        "audio_track_acknowledged": contains_any(lowered, ("audio", "sound", "voice", "speech", "speaking")),
        "speech_like_activity": speech_like_activity,
        "window_0_2_speech_like_activity": window_0_2_speech,
        "window_12_17_speech_like_activity": window_12_17_speech,
        "quiet_or_silent_tail": quiet_or_silent_tail,
        "has_required_time_windows": has_timeline_windows,
        "denies_audio_activity": denies_audio_activity,
    }
    cross_hits = {
        "visual_speaker": contains_any(lowered, cross_groups["visual_speaker"]),
        "concurrent_audio": speech_like_activity,
        "temporal_reference": contains_any(lowered, cross_groups["temporal_reference"]),
        "modality_link": contains_any(lowered, cross_groups["modality_link"]),
        "ending_audio_state": quiet_or_silent_tail,
        "denies_concurrent_audio": denies_audio_activity,
    }

    visual_pass = sum(visual_hits.values()) >= 3
    audio_pass = (
        audio_hits["audio_track_acknowledged"]
        and audio_hits["speech_like_activity"]
        and audio_hits["window_12_17_speech_like_activity"]
        and audio_hits["quiet_or_silent_tail"]
        and audio_hits["has_required_time_windows"]
        and not denies_audio_activity
    )
    cross_modal_pass = (
        visual_pass
        and audio_pass
        and cross_hits["visual_speaker"]
        and cross_hits["concurrent_audio"]
        and cross_hits["temporal_reference"]
        and cross_hits["modality_link"]
        and cross_hits["ending_audio_state"]
        and not denies_audio_activity
    )
    scores: dict[str, dict[str, Any]] = {
        "visual": {
            "status": "PASS" if visual_pass else "FAIL",
            "hits": visual_hits,
            "ground_truth_check_count": len(ground_truth.get("visual_checks", [])),
        },
        "audio": {
            "status": "PASS" if audio_pass else "FAIL",
            "hits": audio_hits,
            "timeline_windows": {
                "0_2s": window_0_2_text,
                "12_17s": window_12_17_text,
                "48_176_50_286s": window_48_50_text,
            },
            "ground_truth_check_count": len(ground_truth.get("audio_checks", [])),
        },
        "cross_modal": {
            "status": "PASS" if cross_modal_pass else "FAIL",
            "hits": cross_hits,
            "ground_truth_check_count": len(ground_truth.get("cross_modal_checks", [])),
        },
    }
    visual_status = str(scores["visual"]["status"])
    audio_status = str(scores["audio"]["status"])
    cross_modal_status = str(scores["cross_modal"]["status"])
    return visual_status, audio_status, cross_modal_status, scores


def classify_error(raw_response: dict[str, Any]) -> tuple[str, str]:
    error_text = json.dumps(raw_response, ensure_ascii=False).lower()
    schema_terms = (
        "schema",
        "unsupported",
        "reject",
        "invalid",
        "video_url",
        "audio_url",
        "input_audio",
        "local file",
        "allowed-local-media-path",
        "truncate",
        "truncated",
        "media",
    )
    runtime_terms = (
        "timeout",
        "timed out",
        "connection refused",
        "connection reset",
        "not ready",
        "readiness",
        "cannot load",
        "crash",
        "unreachable",
    )
    if any(term in error_text for term in schema_terms):
        return "schema_media_failure", "schema_media_failure"
    if any(term in error_text for term in runtime_terms):
        return "serving_runtime_unresolved", "serving_runtime_unresolved"
    return "serving_runtime_unresolved", "serving_runtime_unresolved"


def post_chat_completion(endpoint: str, payload: dict[str, Any], timeout: float) -> tuple[dict[str, Any], float, float]:
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            first_response_ms = (time.perf_counter() - started) * 1000
            body = response.read().decode("utf-8", errors="replace")
            total_ms = (time.perf_counter() - started) * 1000
            return {
                "http_status": response.status,
                "body": json.loads(body) if body else {},
                "body_text": body,
            }, first_response_ms, total_ms
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        total_ms = (time.perf_counter() - started) * 1000
        parsed_body: Any
        try:
            parsed_body = json.loads(body)
        except json.JSONDecodeError:
            parsed_body = None
        return {
            "http_status": exc.code,
            "error": "http_error",
            "body": parsed_body,
            "body_text": body,
        }, total_ms, total_ms
    except (TimeoutError, socket.timeout, urllib.error.URLError) as exc:
        total_ms = (time.perf_counter() - started) * 1000
        return {
            "http_status": None,
            "error": exc.__class__.__name__,
            "message": str(exc),
        }, total_ms, total_ms


def build_evidence(
    args: argparse.Namespace,
    ground_truth: dict[str, Any],
    payload: dict[str, Any],
    request_trace: dict[str, Any],
    raw_response: Any,
    status: str,
    no_go_type: str | None,
    visual_check: str | None,
    audio_check: str | None,
    cross_modal_check: str | None,
    ttft_ms: float | None,
    total_ms: float | None,
    probe_scores: dict[str, Any] | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    del payload
    artifact: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "status": status,
        "no_go_type": no_go_type,
        "model_id": args.model,
        "video_url": args.video_url,
        "fixture_url": args.video_url,
        "file_url": args.video_url,
        "soundtrack_url": args.audio_url,
        "window_audio_urls": locked_window_audio_urls() if args.mode == "video_plus_windowed_soundtracks" else [],
        "window_pack_url": locked_window_pack_audio_url() if args.mode == "video_plus_window_pack_soundtrack" else None,
        "mode": args.mode,
        "prompt_version": PROMPT_VERSION,
        "dry_run": args.dry_run,
        "ground_truth_path": args.ground_truth,
        "ground_truth_source_sha256": ground_truth.get("source_sha256"),
        "request_trace": request_trace,
        "raw_response": raw_response,
        "visual_check": visual_check,
        "audio_check": audio_check,
        "cross_modal_check": cross_modal_check,
        "forbidden_path_checks": request_trace["forbidden_path_checks"],
        "probe_scores": probe_scores or {},
        "ttft_ms": None if ttft_ms is None else round(ttft_ms, 3),
        "total_ms": None if total_ms is None else round(total_ms, 3),
        "streaming_refactor_allowed": status == "gemma4_native_real_video_pass",
        "reason": reason,
        "locked_statuses": sorted(LOCKED_STATUSES),
    }
    post_hits = forbidden_hits(artifact)
    if status == "gemma4_native_real_video_pass" and post_hits:
        artifact["status"] = "proof_invalid"
        artifact["no_go_type"] = "proof_invalid"
        artifact["streaming_refactor_allowed"] = False
        artifact["reason"] = f"forbidden markers present in artifact: {', '.join(post_hits)}"
        path_checks = artifact.get("forbidden_path_checks")
        if isinstance(path_checks, dict):
            path_checks["status"] = "FAIL"
            existing_violations = path_checks.get("violations", [])
            if not isinstance(existing_violations, list):
                existing_violations = []
            path_checks["violations"] = sorted(
                set(existing_violations + [f"forbidden_marker:{hit}" for hit in post_hits])
            )
    return artifact


def write_evidence(path: Path, evidence: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build and optionally submit the locked Gemma4 native real-video proof request."
    )
    parser.add_argument("--base-url", default="http://localhost:8002", help="OpenAI-compatible server base URL")
    parser.add_argument("--model", default="google/gemma-4-E4B-it", help="Gemma4 model id for the request")
    parser.add_argument("--video-url", default=LOCKED_FILE_URL, help="Locked file:// URL for vid_0033.mp4")
    parser.add_argument(
        "--audio-url",
        default=None,
        help="Locked same-fixture soundtrack URL for video_plus_audio_from_same_fixture mode; disallowed for windowed modes",
    )
    parser.add_argument("--ground-truth", required=True, help="Diagnostic ground-truth JSON path")
    parser.add_argument("--out", required=True, help="Output evidence JSON path")
    parser.add_argument("--timeout", type=float, default=300.0, help="HTTP request timeout in seconds")
    parser.add_argument(
        "--mode",
        choices=(
            "direct_video",
            "video_plus_audio_from_same_fixture",
            "video_plus_windowed_soundtracks",
            "video_plus_window_pack_soundtrack",
        ),
        default="direct_video",
        help="Native media request shape to build",
    )
    parser.add_argument("--dry-run", action="store_true", help="Write request/evidence JSON without network I/O")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_path = Path(args.out)
    try:
        ground_truth = load_json(Path(args.ground_truth))
    except (OSError, json.JSONDecodeError) as exc:
        evidence = {
            "schema_version": 1,
            "generated_at": utc_now(),
            "status": "proof_invalid",
            "no_go_type": "proof_invalid",
            "model_id": args.model,
            "video_url": args.video_url,
            "soundtrack_url": args.audio_url,
            "request_trace": None,
            "raw_response": None,
            "visual_check": None,
            "audio_check": None,
            "cross_modal_check": None,
            "forbidden_path_checks": {"status": "FAIL", "violations": ["ground_truth_load_failed"]},
            "ttft_ms": None,
            "total_ms": None,
            "reason": str(exc),
        }
        write_evidence(out_path, evidence)
        print(json.dumps({"out": str(out_path), "status": "proof_invalid", "reason": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    if not isinstance(ground_truth, dict):
        ground_truth = {}

    payload = build_payload(args.model, args.video_url, args.mode, args.audio_url)
    ground_truth_violations = validate_ground_truth(ground_truth)
    fixture_checks = build_forbidden_path_checks(
        args.model, args.video_url, args.audio_url, args.mode, ground_truth_violations
    )
    request_trace = build_request_trace(args, payload, fixture_checks)

    if fixture_checks["status"] != "PASS":
        evidence = build_evidence(
            args,
            ground_truth,
            payload,
            request_trace,
            None,
            "proof_invalid",
            "proof_invalid",
            None,
            None,
            None,
            None,
            None,
            reason="; ".join(fixture_checks["violations"]),
        )
        write_evidence(out_path, evidence)
        print(json.dumps({"out": str(out_path), "status": "proof_invalid", "violations": fixture_checks["violations"]}, ensure_ascii=False, indent=2))
        return 1

    if args.dry_run:
        evidence = build_evidence(
            args,
            ground_truth,
            payload,
            request_trace,
            None,
            "dry_run_valid",
            None,
            None,
            None,
            None,
            None,
            None,
            reason="dry run only; no model request submitted",
        )
        write_evidence(out_path, evidence)
        print(json.dumps({"out": str(out_path), "status": "dry_run_valid", "dry_run": True}, ensure_ascii=False, indent=2))
        return 0

    raw_response, ttft_ms, total_ms = post_chat_completion(request_trace["endpoint"], payload, args.timeout)
    if raw_response.get("error") or raw_response.get("http_status") not in (200, None):
        status, no_go_type = classify_error(raw_response)
        evidence = build_evidence(
            args,
            ground_truth,
            payload,
            request_trace,
            raw_response,
            status,
            no_go_type,
            None,
            None,
            None,
            ttft_ms,
            total_ms,
            reason="model request did not complete as a valid chat response",
        )
        write_evidence(out_path, evidence)
        print(json.dumps({"out": str(out_path), "status": status, "no_go_type": no_go_type}, ensure_ascii=False, indent=2))
        return 0

    response_body = raw_response.get("body", {})
    answer = extract_answer(response_body)
    visual_check, audio_check, cross_modal_check, probe_scores = evaluate_answer(answer, ground_truth)
    all_checks_pass = visual_check == "PASS" and audio_check == "PASS" and cross_modal_check == "PASS"
    status = "gemma4_native_real_video_pass" if all_checks_pass else "gemma4_capability_no_go"
    no_go_type = None if all_checks_pass else "gemma4_capability_no_go"
    evidence = build_evidence(
        args,
        ground_truth,
        payload,
        request_trace,
        raw_response,
        status,
        no_go_type,
        visual_check,
        audio_check,
        cross_modal_check,
        ttft_ms,
        total_ms,
        probe_scores=probe_scores,
        reason=None if all_checks_pass else "native request completed but at least one diagnostic check failed",
    )
    write_evidence(out_path, evidence)
    print(json.dumps({"out": str(out_path), "status": evidence["status"], "no_go_type": evidence["no_go_type"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
