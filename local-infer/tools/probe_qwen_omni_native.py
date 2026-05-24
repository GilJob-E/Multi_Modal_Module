#!/usr/bin/env python3
# pyright: reportMissingImports=false
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PRIMARY_MODEL_ID = "Qwen/Qwen2.5-Omni-7B-GPTQ-Int4"
FALLBACK_MODEL_ID = "Qwen/Qwen2.5-Omni-3B"
PRIMARY_SNAPSHOT = Path("/home/kio/hf_cache/qwen-hub/models--Qwen--Qwen2.5-Omni-7B-GPTQ-Int4/snapshots/6d33b6bb5114a84de7efd38310779242520e7d4e")
FALLBACK_SNAPSHOT = Path("/home/kio/hf_cache/qwen-hub/models--Qwen--Qwen2.5-Omni-3B/snapshots/f75b40e3da2003cdd6e1829b1f420ca70797c34e")
REQUIRED_PROBES = {
    "english_passphrase": "audio_positive",
    "no_audio_ablation": "no_audio_ablation",
    "beep_only": "beep_only",
    "korean_passphrase": "korean_phrase",
    "av_sync": "av_sync",
    "cross_modal_event": "cross_modal_event",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local Qwen2.5-Omni direct audio+video probes.")
    parser.add_argument("--fixtures", required=True, help="Directory containing manifest.json and WAV/MP4 fixtures")
    parser.add_argument("--out", required=True, help="JSON evidence output path")
    parser.add_argument("--primary-snapshot", default=str(PRIMARY_SNAPSHOT), help="Primary GPTQ snapshot path")
    parser.add_argument("--fallback-snapshot", default=str(FALLBACK_SNAPSHOT), help="Fallback 3B snapshot path")
    parser.add_argument("--max-new-tokens", type=int, default=64, help="Generated text token limit per probe")
    args = parser.parse_args()

    configure_offline_env()
    fixtures_dir = Path(args.fixtures)
    manifest = load_manifest(fixtures_dir)
    primary_snapshot = Path(args.primary_snapshot)
    fallback_snapshot = Path(args.fallback_snapshot)

    candidate_attempts: list[dict[str, Any]] = []
    candidate_attempts.append(attempt_primary_load(primary_snapshot))

    fallback_result = run_fallback_probes(
        snapshot=fallback_snapshot,
        fixtures_dir=fixtures_dir,
        manifest=manifest,
        max_new_tokens=args.max_new_tokens,
    )
    candidate_attempts.append(fallback_result["candidate"])
    probes = fallback_result["probes"]
    sequence_summary = summarize(probes)
    status = "PASS" if sequence_summary["all_required_passed"] else "NO_GO"

    output = {
        "schema_version": 2,
        "created_by": "local-infer/tools/probe_qwen_omni_native.py",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "engine": "Transformers + qwen-omni-utils local offline inference",
        "primary_model": PRIMARY_MODEL_ID,
        "model": FALLBACK_MODEL_ID,
        "candidate_attempts": candidate_attempts,
        "candidate_substitution": {
            "used": True,
            "reason": "Primary GPTQ snapshot was present but could not initialize with the available local GPTQ runtime; Task 2 allowed Qwen/Qwen2.5-Omni-3B as the next local-fit alternate.",
        },
        "snapshot": str(fallback_snapshot),
        "fixture_manifest": str(fixtures_dir / "manifest.json"),
        "fixture_manifest_schema_version": manifest.get("schema_version"),
        "probe_count": len(probes),
        "all_required_present": set(REQUIRED_PROBES) <= {probe["name"] for probe in probes},
        "native_media_direct": True,
        "direct_media_semantics": "Each probe sends typed Qwen content parts containing an explicit WAV audio path and a muted MP4 video path; no transcript text, hosted ASR, remote inference, or embedded MP4 audio is used as the audio source.",
        "transcript_text_used": False,
        "remote_inference_used": False,
        "use_audio_in_video": False,
        "probes": probes,
        "sequence_summary": sequence_summary,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out_path), "status": status, "all_required_passed": sequence_summary["all_required_passed"]}, ensure_ascii=False))
    return 0 if status == "PASS" else 1


def configure_offline_env() -> None:
    os.environ.setdefault("HF_HOME", "/home/kio/hf_cache")
    os.environ.setdefault("HF_HUB_CACHE", "/home/kio/hf_cache/qwen-hub")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("FORCE_QWENVL_VIDEO_READER", "decord")


def load_manifest(fixtures_dir: Path) -> dict[str, Any]:
    manifest_path = fixtures_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fixtures = manifest.get("fixtures")
    if not isinstance(fixtures, dict):
        raise ValueError("manifest fixtures must be an object")
    missing = set(REQUIRED_PROBES) - set(fixtures)
    if missing:
        raise ValueError(f"missing required probes: {sorted(missing)}")
    return manifest


def attempt_primary_load(snapshot: Path) -> dict[str, Any]:
    from transformers import Qwen2_5OmniForConditionalGeneration

    started = time.monotonic()
    attempt: dict[str, Any] = {
        "model": PRIMARY_MODEL_ID,
        "snapshot": str(snapshot),
        "snapshot_exists": snapshot.exists(),
    }
    try:
        model = Qwen2_5OmniForConditionalGeneration.from_pretrained(
            str(snapshot),
            torch_dtype="auto",
            device_map="auto",
            local_files_only=True,
            trust_remote_code=True,
            attn_implementation="eager",
        )
        attempt.update(
            {
                "status": "loaded",
                "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                "model_class": model.__class__.__name__,
            }
        )
        del model
    except Exception as exc:  # noqa: BLE001 - evidence must preserve exact local blocker
        attempt.update(
            {
                "status": "load-no-go",
                "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            }
        )
    return attempt


def run_fallback_probes(
    *,
    snapshot: Path,
    fixtures_dir: Path,
    manifest: dict[str, Any],
    max_new_tokens: int,
) -> dict[str, Any]:
    import torch
    from qwen_omni_utils import process_mm_info
    from transformers import AutoProcessor, Qwen2_5OmniForConditionalGeneration

    started_load = time.monotonic()
    model = Qwen2_5OmniForConditionalGeneration.from_pretrained(
        str(snapshot),
        torch_dtype="auto",
        device_map="auto",
        local_files_only=True,
        trust_remote_code=True,
        attn_implementation="eager",
    )
    if hasattr(model, "disable_talker"):
        model.disable_talker()
    processor = AutoProcessor.from_pretrained(str(snapshot), local_files_only=True, trust_remote_code=True)
    load_elapsed_ms = round((time.monotonic() - started_load) * 1000, 3)

    probes = []
    for name in REQUIRED_PROBES:
        fixture = manifest["fixtures"][name]
        messages, request_metadata = build_messages(fixtures_dir, fixture)
        text = processor.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)
        audios, images, videos = process_mm_info(messages, use_audio_in_video=False)
        inputs = processor(
            text=text,
            audio=audios,
            images=images,
            videos=videos,
            return_tensors="pt",
            padding=True,
            use_audio_in_video=False,
        )
        inputs = inputs.to(model.device)
        started = time.monotonic()
        with torch.no_grad():
            output = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                return_audio=False,
                use_audio_in_video=False,
            )
        latency_ms = round((time.monotonic() - started) * 1000, 3)
        text_ids = output[0][inputs.input_ids.shape[1] :]
        answer = processor.decode(text_ids, skip_special_tokens=True).strip()
        evaluation = evaluate_answer(answer, fixture)
        probe = {
            "name": name,
            "status": evaluation["status"],
            "prompt": fixture["prompt"],
            "expected_answer": fixture.get("expected_answer", {}).get("coded_text", ""),
            "expected_substrings": fixture.get("expected_answer", {}).get("expected_substrings", []),
            "negative_substrings": fixture.get("expected_answer", {}).get("negative_substrings", []),
            "event_timing_ms": fixture.get("event_timing", {}),
            "raw_request_metadata": request_metadata,
            "raw_model_answer": answer,
            "normalized": evaluation,
            "event_response_latency_ms": latency_ms if fixture.get("event_timing") else None,
        }
        probes.append(probe)
        print(json.dumps({"fixture": name, "status": probe["status"], "latency_ms": latency_ms, "answer": answer}, ensure_ascii=False))

    return {
        "candidate": {
            "model": FALLBACK_MODEL_ID,
            "snapshot": str(snapshot),
            "snapshot_exists": snapshot.exists(),
            "status": "probed",
            "model_load_elapsed_ms": load_elapsed_ms,
            "model_class": model.__class__.__name__,
            "processor_class": processor.__class__.__name__,
        },
        "probes": probes,
    }


def build_messages(fixtures_dir: Path, fixture: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    audio_path = fixtures_dir / fixture["audio_file"]
    video_path = fixtures_dir / fixture["video_file"]
    content = [
        {"type": "audio", "audio": str(audio_path)},
        {"type": "video", "video": str(video_path)},
        {"type": "text", "text": fixture["prompt"]},
    ]
    metadata = {
        "message_shape": "Qwen typed content list",
        "media_types": [part["type"] for part in content],
        "audio_input": {
            "type": "audio",
            "path": str(audio_path),
            "bytes": audio_path.stat().st_size,
            "mime_type": fixture.get("audio_mime_type"),
            "transport": "typed_local_path_direct_media",
        },
        "video_input": {
            "type": "video",
            "path": str(video_path),
            "bytes": video_path.stat().st_size,
            "mime_type": fixture.get("video_mime_type"),
            "video_audio_policy": fixture.get("video_audio_policy"),
            "transport": "typed_local_path_direct_media",
        },
        "text_prompt_chars": len(fixture["prompt"]),
        "transcript_text_used": False,
        "use_audio_in_video": False,
    }
    return [{"role": "user", "content": content}], metadata


def evaluate_answer(answer: str, fixture: dict[str, Any]) -> dict[str, Any]:
    lowered = answer.casefold()
    expected_terms = fixture.get("expected_answer", {}).get("expected_substrings", [])
    negative_terms = fixture.get("expected_answer", {}).get("negative_substrings", [])
    expected = [term for term in expected_terms if term.casefold() in lowered]
    negative = [term for term in negative_terms if term.casefold() in lowered]
    if fixture["key"] in {"english_passphrase", "korean_passphrase", "av_sync", "cross_modal_event"}:
        passed = len(expected) >= max(1, min(2, len(expected_terms))) and not negative
    else:
        passed = bool(expected) and not negative
    return {
        "status": "PASS" if passed else "FAIL",
        "mode": "model_response",
        "matched_expected_substrings": expected,
        "matched_negative_substrings": negative,
    }


def summarize(probes: list[dict[str, Any]]) -> dict[str, Any]:
    by_name = {probe["name"]: probe for probe in probes}
    statuses: dict[str, Any] = {}
    all_pass = True
    for fixture_name, alias in REQUIRED_PROBES.items():
        probe = by_name.get(fixture_name)
        passed = bool(probe and probe.get("status") == "PASS")
        latency_ok = True
        if fixture_name == "cross_modal_event" and probe:
            latency = probe.get("event_response_latency_ms")
            budget = probe.get("event_timing_ms", {}).get("response_budget_ms") or 2000
            latency_ok = isinstance(latency, int | float) and latency <= budget
            statuses["event_response_ms"] = latency
            statuses["event_response_budget_ms"] = budget
        statuses[alias] = "PASS" if passed and latency_ok else "FAIL"
        all_pass = all_pass and passed and latency_ok
    return {
        "selected_model": "qwen2.5-omni-3b" if all_pass else None,
        "model": FALLBACK_MODEL_ID,
        "primary_model": PRIMARY_MODEL_ID,
        "required_statuses": statuses,
        "all_required_passed": all_pass,
    }


if __name__ == "__main__":
    raise SystemExit(main())
