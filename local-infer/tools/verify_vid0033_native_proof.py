#!/usr/bin/env python3
from __future__ import annotations

"""Deterministic classifier for the Gemma4 native real-video proof gate.

The verifier writes a classified JSON artifact to ``--out`` and exits with a
nonzero status when the proof is ``proof_invalid``. This is intentional so the
script can be used as a strict gate in shell pipelines.
"""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
    "/audio",
    "/frames",
    "audio_analysis",
    "cross_modal_event",
    "sample30.mp4",
    "native_success=false",
)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing proof artifact: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {path}") from exc


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
    elif isinstance(value, tuple):
        for item in value:
            strings.extend(flatten_strings(item))
    return strings


def compact_text(value: str) -> str:
    return re.sub(r"\s+", "", value.lower())


def collect_forbidden_hits(data: Any) -> list[str]:
    flattened = "\n".join(flatten_strings(data)).lower()
    compacted = compact_text(json.dumps(data, ensure_ascii=False, sort_keys=True))
    hits: list[str] = []
    for marker in FORBIDDEN_MARKERS:
        if marker in flattened or marker in compacted:
            hits.append(marker)
    return hits


def status_from_field(data: dict[str, Any]) -> str | None:
    status = data.get("status")
    return status if isinstance(status, str) else None


def is_gemma4_model(model_id: Any) -> bool:
    return isinstance(model_id, str) and model_id.startswith("google/gemma-4-")


def is_exact_fixture_url(value: Any) -> bool:
    return value == "file:///workspace/gje/vid_0033.mp4"


def check_flag(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "pass":
            return True
        if lowered == "fail":
            return False
    return None


def classify(data: Any) -> tuple[str, list[str], dict[str, Any]]:
    details: dict[str, Any] = {}

    if not isinstance(data, dict):
        return "proof_invalid", ["proof artifact must be a JSON object"], details

    explicit_status = status_from_field(data)
    forbidden_hits = collect_forbidden_hits(data)
    details["forbidden_path_checks"] = {
        "status": "FAIL" if forbidden_hits else "PASS",
        "checked_terms": list(FORBIDDEN_MARKERS),
        "violations": forbidden_hits,
    }

    if forbidden_hits:
        return "proof_invalid", [f"forbidden markers present: {', '.join(forbidden_hits)}"], details

    if explicit_status == "proof_invalid":
        return "proof_invalid", ["proof artifact already marked invalid"], details

    if explicit_status == "serving_runtime_unresolved":
        return "serving_runtime_unresolved", ["artifact explicitly marked serving/runtime unresolved"], details

    if explicit_status == "schema_media_failure":
        return "schema_media_failure", ["artifact explicitly marked schema/media failure"], details

    if explicit_status == "gemma4_capability_no_go":
        return "gemma4_capability_no_go", ["artifact explicitly marked Gemma4 capability no-go"], details

    model_id = data.get("model_id")
    fixture_url = data.get("video_url") or data.get("fixture_url") or data.get("file_url")
    request_trace = data.get("request_trace")
    raw_response = data.get("raw_response")
    visual_check = check_flag(data.get("visual_check"))
    audio_check = check_flag(data.get("audio_check"))
    cross_modal_check = check_flag(data.get("cross_modal_check"))
    native_success = check_flag(data.get("native_success"))
    streaming_allowed = check_flag(data.get("streaming_refactor_allowed"))

    if explicit_status == "gemma4_native_real_video_pass" or streaming_allowed is True:
        if not is_gemma4_model(model_id):
            return "proof_invalid", ["pass artifact must use a Gemma4 model id"], details
        if not is_exact_fixture_url(fixture_url):
            return "proof_invalid", ["pass artifact must use file:///workspace/gje/vid_0033.mp4"], details
        if not request_trace:
            return "proof_invalid", ["pass artifact must include request_trace"], details
        if raw_response is None:
            return "proof_invalid", ["pass artifact must include raw_response"], details
        if visual_check is not True or audio_check is not True or cross_modal_check is not True:
            return "proof_invalid", ["pass artifact must have all visual/audio/cross-modal checks passing"], details
        return "gemma4_native_real_video_pass", ["pass artifact satisfies the locked proof contract"], details

    if explicit_status == "gemma4_native_real_video_pass":
        return "proof_invalid", ["pass status without a valid pass contract"], details

    failure_reason = str(data.get("failure_reason", "")).lower()
    event_reason = str(data.get("reason", "")).lower()
    probe_summary = json.dumps(data.get("probe_scores", {}), ensure_ascii=False).lower()

    if any(term in failure_reason for term in ("readiness", "timeout", "connection reset", "crash", "cannot load", "cannot see", "not ready")):
        return "serving_runtime_unresolved", ["readiness/runtime failure before a valid native request"], details
    if any(term in event_reason for term in ("readiness", "timeout", "connection reset", "crash", "cannot load", "cannot see", "not ready")):
        return "serving_runtime_unresolved", ["readiness/runtime failure before a valid native request"], details

    if any(term in probe_summary for term in ("schema", "reject", "unsupported", "truncate", "truncated", "input_audio", "audio_url", "video_url", "local file")):
        return "schema_media_failure", ["native media schema or container handling failed"], details

    if any(value is False for value in (visual_check, audio_check, cross_modal_check)):
        return "gemma4_capability_no_go", ["native request completed but at least one required check failed"], details

    if native_success is False:
        return "proof_invalid", ["native_success=false cannot count as proof pass"], details

    if is_gemma4_model(model_id) and is_exact_fixture_url(fixture_url) and all(value is True for value in (visual_check, audio_check, cross_modal_check)):
        return "gemma4_native_real_video_pass", ["locked pass contract satisfied"], details

    if model_id is not None and not is_gemma4_model(model_id):
        return "proof_invalid", ["non-Gemma model cannot satisfy the proof gate"], details

    if fixture_url is not None and not is_exact_fixture_url(fixture_url):
        return "proof_invalid", ["wrong fixture URL cannot satisfy the proof gate"], details

    if request_trace is None:
        return "proof_invalid", ["missing request_trace"], details

    return "proof_invalid", ["artifact does not satisfy any locked proof status"], details


def build_output(proof_path: Path, data: Any) -> tuple[dict[str, Any], bool]:
    status, reasons, details = classify(data)
    output = {
        "status": status,
        "streaming_refactor_allowed": status == "gemma4_native_real_video_pass",
        "reasons": reasons,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "proof_path": str(proof_path),
        "forbidden_path_checks": details.get("forbidden_path_checks", {}),
        "locked_statuses": sorted(LOCKED_STATUSES),
    }
    return output, status == "proof_invalid"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Classify the vid_0033 native proof artifact into the locked Gemma4 gate statuses.",
        epilog="Writes classified JSON to --out. Exits nonzero when the classification is proof_invalid.",
    )
    parser.add_argument("--proof", required=True, help="Input proof JSON path")
    parser.add_argument("--out", required=True, help="Output JSON path")
    args = parser.parse_args()

    proof_path = Path(args.proof)
    out_path = Path(args.out)
    try:
        data = load_json(proof_path)
        output, should_fail = build_output(proof_path, data)
    except ValueError as exc:
        output = {
            "status": "proof_invalid",
            "streaming_refactor_allowed": False,
            "reasons": [str(exc)],
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "proof_path": str(proof_path),
            "forbidden_path_checks": {
                "status": "FAIL",
                "checked_terms": list(FORBIDDEN_MARKERS),
                "violations": [],
            },
            "locked_statuses": sorted(LOCKED_STATUSES),
        }
        should_fail = True

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 1 if should_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
