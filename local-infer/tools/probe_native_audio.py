#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REQUIRED_PROBES = [
    "english_passphrase",
    "korean_passphrase",
    "no_audio_ablation",
    "beep_only",
    "av_sync",
    "cross_modal_event",
]
DEFAULT_MODEL = "google/gemma-4-E4B-it"


class ProbeError(RuntimeError):
    pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Run native explicit-audio AV probes against an OpenAI-compatible server.")
    parser.add_argument("--base-url", default="http://localhost:8002", help="OpenAI-compatible server base URL")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model name for /v1/chat/completions")
    parser.add_argument("--fixtures", required=True, help="Directory containing manifest.json and generated fixtures")
    parser.add_argument("--out", required=True, help="JSON evidence output path")
    parser.add_argument("--expect-no-audio", action="store_true", help="Treat audio-positive failures as expected negative evidence")
    parser.add_argument("--dry-run", action="store_true", help="Validate fixtures and payloads without contacting a model")
    parser.add_argument(
        "--audio-url-prefix",
        default=None,
        help="Optional local URL prefix for WAV files; when set, use audio_url instead of input_audio",
    )
    args = parser.parse_args()

    fixtures_dir = Path(args.fixtures)
    manifest = load_manifest(fixtures_dir)
    results = []
    for key in REQUIRED_PROBES:
        fixture = manifest["fixtures"][key]
        payload, request_metadata = build_payload(
            model=args.model,
            fixtures_dir=fixtures_dir,
            fixture=fixture,
            base_url=args.base_url,
            audio_url_prefix=args.audio_url_prefix,
        )
        validation = validate_fixture_and_payload(fixtures_dir, fixture, payload, request_metadata)
        if args.dry_run:
            raw_response = None
            raw_answer = None
            timings = {"request_total_ms": None, "first_response_ms": None}
            evaluation = dry_run_evaluation(validation)
        else:
            raw_response, timings = post_chat_completion(args.base_url, payload, timeout=300)
            raw_answer = extract_answer(raw_response)
            evaluation = evaluate_answer(raw_answer, fixture, args.expect_no_audio, validation)
        results.append(
            probe_record(
                key=key,
                fixture=fixture,
                request_metadata=request_metadata,
                validation=validation,
                raw_response=raw_response,
                raw_answer=raw_answer,
                timings=timings,
                evaluation=evaluation,
            )
        )

    summary = summarize(results, args.expect_no_audio)
    output: dict[str, Any] = {
        "schema_version": 1,
        "created_by": "local-infer/tools/probe_native_audio.py",
        "dry_run": args.dry_run,
        "expect_no_audio": args.expect_no_audio,
        "base_url": args.base_url,
        "model": args.model,
        "fixtures_dir": str(fixtures_dir),
        "fixture_manifest_sha256": sha256_file(fixtures_dir / "manifest.json"),
        "required_probes": REQUIRED_PROBES,
        "summary": summary,
        "probes": results,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out_path), "status": summary["status"]}, ensure_ascii=False))
    if summary["status"] != "PASS":
        raise SystemExit(1)


def load_manifest(fixtures_dir: Path) -> dict[str, Any]:
    manifest_path = fixtures_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ProbeError(f"manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fixtures = manifest.get("fixtures")
    if not isinstance(fixtures, dict):
        raise ProbeError("manifest fixtures must be an object")
    keys = set(fixtures)
    required = set(REQUIRED_PROBES)
    if keys != required:
        raise ProbeError(f"manifest fixture keys must be exactly {sorted(required)}, got {sorted(keys)}")
    return manifest


def build_payload(
    *,
    model: str,
    fixtures_dir: Path,
    fixture: dict[str, Any],
    base_url: str,
    audio_url_prefix: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    audio_path = fixtures_dir / fixture["audio_file"]
    video_path = fixtures_dir / fixture["video_file"]
    video_b64 = base64.b64encode(video_path.read_bytes()).decode("ascii")
    content = [
        {
            "type": "video_url",
            "video_url": {"url": f"data:video/mp4;base64,{video_b64}"},
        }
    ]
    if audio_url_prefix:
        content.append(
            {
                "type": "audio_url",
                "audio_url": {"url": f"{audio_url_prefix.rstrip('/')}/{fixture['audio_file']}"},
            }
        )
        audio_transport = "audio_url"
    else:
        audio_b64 = base64.b64encode(audio_path.read_bytes()).decode("ascii")
        content.append(
            {
                "type": "input_audio",
                "input_audio": {"data": audio_b64, "format": "wav"},
            }
        )
        audio_transport = "input_audio"
    content.append({"type": "text", "text": fixture["prompt"]})
    payload = {
        "model": model,
        "stream": False,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 256,
        "temperature": 0,
    }
    payload_bytes = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    metadata = {
        "endpoint": f"{base_url.rstrip('/')}/v1/chat/completions",
        "method": "POST",
        "model": model,
        "fixture_key": fixture["key"],
        "payload_sha256": hashlib.sha256(payload_bytes).hexdigest(),
        "payload_size_bytes": len(payload_bytes),
        "content_parts": summarize_content_parts(content),
        "audio_transport": audio_transport,
        "raw_request_generation": {
            "stream": False,
            "max_tokens": 256,
            "temperature": 0,
        },
    }
    return payload, metadata


def summarize_content_parts(content: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary = []
    for part in content:
        part_type = part.get("type")
        if part_type == "video_url":
            url = part["video_url"]["url"]
            summary.append({"type": "video_url", "media_type": "video/mp4", "url_prefix": url[:32], "data_url": url.startswith("data:video/mp4;base64,")})
        elif part_type == "input_audio":
            audio = part["input_audio"]
            summary.append({"type": "input_audio", "format": audio.get("format"), "base64_bytes": len(audio.get("data", ""))})
        elif part_type == "audio_url":
            summary.append({"type": "audio_url", "url": part["audio_url"]["url"], "media_type": "audio/wav"})
        elif part_type == "text":
            summary.append({"type": "text", "chars": len(part.get("text", ""))})
    return summary


def validate_fixture_and_payload(
    fixtures_dir: Path,
    fixture: dict[str, Any],
    payload: dict[str, Any],
    request_metadata: dict[str, Any],
) -> dict[str, Any]:
    violations = []
    audio_path = fixtures_dir / fixture.get("audio_file", "")
    video_path = fixtures_dir / fixture.get("video_file", "")
    if not audio_path.is_file():
        violations.append("audio_file_missing")
    if not video_path.is_file():
        violations.append("video_file_missing")
    if audio_path.suffix.lower() != ".wav":
        violations.append("audio_file_not_wav")
    if video_path.suffix.lower() != ".mp4":
        violations.append("video_file_not_mp4")
    if fixture.get("audio_mime_type") != "audio/wav":
        violations.append("audio_mime_type_not_wav")
    if fixture.get("video_mime_type") != "video/mp4":
        violations.append("video_mime_type_not_mp4")

    expected = fixture.get("expected_answer", {})
    if not expected.get("expected_substrings"):
        violations.append("expected_substrings_missing")
    if expected.get("machine_check") != "casefold_substring_match":
        violations.append("machine_check_not_supported")
    if fixture["key"] == "cross_modal_event":
        timing = fixture.get("event_timing", {})
        if timing.get("response_budget_ms") != 2000:
            violations.append("cross_modal_response_budget_not_2000ms")
        for required_key in ["target_event_start_ms", "target_event_end_ms", "audio_cue_ms", "visual_cue_ms"]:
            if required_key not in timing:
                violations.append(f"cross_modal_timing_missing:{required_key}")

    content = payload["messages"][0]["content"]
    part_types = [part.get("type") for part in content]
    if part_types[:2] not in (["video_url", "input_audio"], ["video_url", "audio_url"]):
        violations.append("payload_missing_video_then_audio")
    if part_types[-1] != "text":
        violations.append("payload_missing_final_text")
    if "input_audio" in part_types:
        audio_part = next(part for part in content if part.get("type") == "input_audio")
        if audio_part["input_audio"].get("format") != "wav":
            violations.append("input_audio_format_not_wav")
        try:
            decoded = base64.b64decode(audio_part["input_audio"].get("data", ""), validate=True)
            if not decoded.startswith(b"RIFF"):
                violations.append("input_audio_not_riff_wav")
        except ValueError:
            violations.append("input_audio_base64_invalid")
    if request_metadata.get("audio_transport") not in {"input_audio", "audio_url"}:
        violations.append("audio_transport_invalid")

    guessed_audio_type = mimetypes.guess_type(str(audio_path))[0]
    guessed_video_type = mimetypes.guess_type(str(video_path))[0]
    return {
        "status": "PASS" if not violations else "FAIL",
        "violations": violations,
        "media_types": {
            "audio_manifest": fixture.get("audio_mime_type"),
            "audio_guess": guessed_audio_type or "audio/wav",
            "video_manifest": fixture.get("video_mime_type"),
            "video_guess": guessed_video_type or "video/mp4",
        },
        "expected_substrings": expected.get("expected_substrings", []),
        "negative_substrings": expected.get("negative_substrings", []),
        "event_timing": fixture.get("event_timing", {}),
    }


def dry_run_evaluation(validation: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": validation["status"],
        "mode": "dry_run_validation",
        "passed_checks": validation["status"] == "PASS",
        "matched_expected_substrings": [],
        "matched_negative_substrings": [],
    }


def post_chat_completion(base_url: str, payload: dict[str, Any], timeout: float) -> tuple[dict[str, Any], dict[str, float | None]]:
    endpoint = f"{base_url.rstrip('/')}/v1/chat/completions"
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            first_response_ms = round((time.perf_counter() - started) * 1000, 1)
            body_text = response.read().decode("utf-8", errors="replace")
            total_ms = round((time.perf_counter() - started) * 1000, 1)
            try:
                body = json.loads(body_text) if body_text else {}
            except json.JSONDecodeError:
                body = {"unparsed_body": body_text}
            return {"http_status": response.status, "body": body, "body_text": body_text}, {
                "first_response_ms": first_response_ms,
                "request_total_ms": total_ms,
            }
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        total_ms = round((time.perf_counter() - started) * 1000, 1)
        return {"http_status": exc.code, "error": "http_error", "body_text": body_text}, {
            "first_response_ms": total_ms,
            "request_total_ms": total_ms,
        }
    except (TimeoutError, socket.timeout, urllib.error.URLError) as exc:
        total_ms = round((time.perf_counter() - started) * 1000, 1)
        return {"http_status": None, "error": exc.__class__.__name__, "message": str(exc)}, {
            "first_response_ms": total_ms,
            "request_total_ms": total_ms,
        }


def extract_answer(raw_response: dict[str, Any]) -> str:
    body = raw_response.get("body")
    if not isinstance(body, dict):
        return ""
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content", "")
        return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    text = first.get("text", "")
    return text if isinstance(text, str) else ""


def evaluate_answer(answer: str, fixture: dict[str, Any], expect_no_audio: bool, validation: dict[str, Any]) -> dict[str, Any]:
    lowered = answer.casefold()
    expected = [term for term in validation["expected_substrings"] if term.casefold() in lowered]
    negative = [term for term in validation["negative_substrings"] if term.casefold() in lowered]
    expected_terms = validation["expected_substrings"]
    normal_pass = validation["status"] == "PASS" and bool(expected) and not negative
    if fixture["key"] in {"english_passphrase", "korean_passphrase", "av_sync", "cross_modal_event"}:
        normal_pass = validation["status"] == "PASS" and len(expected) >= max(1, min(2, len(expected_terms))) and not negative
    if expect_no_audio and fixture["key"] in {"english_passphrase", "korean_passphrase", "av_sync", "cross_modal_event"}:
        status = "PASS" if not normal_pass else "FAIL"
    else:
        status = "PASS" if normal_pass else "FAIL"
    return {
        "status": status,
        "mode": "model_response",
        "matched_expected_substrings": expected,
        "matched_negative_substrings": negative,
        "expect_no_audio_applied": expect_no_audio,
    }


def probe_record(
    *,
    key: str,
    fixture: dict[str, Any],
    request_metadata: dict[str, Any],
    validation: dict[str, Any],
    raw_response: dict[str, Any] | None,
    raw_answer: str | None,
    timings: dict[str, Any],
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    event_timing = fixture.get("event_timing", {})
    event_response_latency_ms = None
    if timings.get("first_response_ms") is not None and event_timing.get("target_event_start_ms") is not None:
        event_response_latency_ms = timings["first_response_ms"]
    return {
        "key": key,
        "status": evaluation["status"],
        "fixture_files": fixture.get("files", {}),
        "request_metadata": request_metadata,
        "validation": validation,
        "raw_model_answer": raw_answer,
        "raw_response_metadata": raw_response,
        "normalized": evaluation,
        "timings_ms": timings,
        "event_response_latency_ms": event_response_latency_ms,
        "event_response_budget_ms": event_timing.get("response_budget_ms"),
    }


def summarize(results: list[dict[str, Any]], expect_no_audio: bool) -> dict[str, Any]:
    statuses = {result["key"]: result["status"] for result in results}
    cross = next((result for result in results if result["key"] == "cross_modal_event"), None)
    return {
        "status": "PASS" if all(status == "PASS" for status in statuses.values()) else "FAIL",
        "probe_statuses": statuses,
        "expect_no_audio": expect_no_audio,
        "event_response_ms": None if cross is None else cross.get("event_response_latency_ms"),
        "event_response_budget_ms": None if cross is None else cross.get("event_response_budget_ms"),
    }


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    main()
