#!/usr/bin/env python3
# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportAny=false, reportExplicitAny=false, reportUnusedCallResult=false
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch
from qwen_omni_utils import process_mm_info
from transformers import AutoProcessor, Qwen2_5OmniForConditionalGeneration

MODEL_ID = "Qwen/Qwen2.5-Omni-3B"
PRIMARY_MODEL_ID = "Qwen/Qwen2.5-Omni-7B-GPTQ-Int4"
SNAPSHOT = Path("/home/kio/hf_cache/qwen-hub/models--Qwen--Qwen2.5-Omni-3B/snapshots/f75b40e3da2003cdd6e1829b1f420ca70797c34e")
FIXTURES_DIR = Path(".sisyphus/evidence/audio-fixtures")
OUT = Path(".sisyphus/evidence/task-5-qwen-native-probe.json")

REQUIRED_PROBES = {
    "english_passphrase": "audio_positive",
    "no_audio_ablation": "no_audio_ablation",
    "beep_only": "beep_only",
    "korean_passphrase": "korean_phrase",
    "av_sync": "av_sync",
    "cross_modal_event": "cross_modal_event",
}

os.environ["HF_HOME"] = "/home/kio/hf_cache"
os.environ["HF_HUB_CACHE"] = "/home/kio/hf_cache/qwen-hub"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"


def normalize_pass(answer: str, expected: list[str], fixture_name: str) -> bool:
    lowered = answer.lower()
    if fixture_name == "no_audio_ablation":
        return any(term in lowered for term in ("no audio", "silent", "silence"))
    if fixture_name in {"english_passphrase", "korean_passphrase", "av_sync", "cross_modal_event"}:
        negative_markers = ("do not", "don't", "not hear", "not detected", "no,", "cannot")
        if any(marker in lowered for marker in negative_markers):
            return False
    return any(substr.lower() in lowered for substr in expected)


def build_messages(fixture: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    audio_path = FIXTURES_DIR / fixture["media"]["audio_wav"]["path"]
    content: list[dict[str, Any]] = [{"type": "audio", "audio": str(audio_path)}]
    image_count = 0
    for frame in fixture["media"].get("frames_jpeg", []):
        content.append({"type": "image", "image": str(FIXTURES_DIR / frame["path"])})
        image_count += 1
    content.append({"type": "text", "text": fixture["prompt"]})
    metadata = {
        "message_shape": "Qwen typed content list",
        "media_types": [part["type"] for part in content],
        "audio_input": {
            "type": "audio",
            "path": str(audio_path),
            "bytes": audio_path.stat().st_size,
            "sample_rate_hz": fixture["audio"].get("sample_rate_hz"),
            "duration_ms": fixture["audio"].get("duration_ms"),
        },
        "image_frames": image_count,
        "text_prompt_chars": len(fixture["prompt"]),
        "transcript_text_used": False,
        "use_audio_in_video": False,
    }
    return [{"role": "user", "content": content}], metadata


def main() -> None:
    manifest = json.loads((FIXTURES_DIR / "manifest.json").read_text(encoding="utf-8"))
    started_load = time.monotonic()
    model = Qwen2_5OmniForConditionalGeneration.from_pretrained(
        str(SNAPSHOT),
        torch_dtype="auto",
        device_map="auto",
        local_files_only=True,
        trust_remote_code=True,
        attn_implementation="eager",
    )
    if hasattr(model, "disable_talker"):
        model.disable_talker()
    processor = AutoProcessor.from_pretrained(str(SNAPSHOT), local_files_only=True, trust_remote_code=True)
    load_elapsed_ms = round((time.monotonic() - started_load) * 1000, 3)

    probes: list[dict[str, Any]] = []
    for name, fixture in manifest["fixtures"].items():
        messages, request_metadata = build_messages(fixture)
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
        inputs = inputs.to(model.device).to(model.dtype)
        started = time.monotonic()
        with torch.no_grad():
            output = model.generate(
                **inputs,
                max_new_tokens=64,
                do_sample=False,
                return_audio=False,
                use_audio_in_video=False,
            )
        latency_ms = round((time.monotonic() - started) * 1000, 3)
        text_ids = output[0][inputs.input_ids.shape[1] :]
        answer = processor.decode(text_ids, skip_special_tokens=True).strip()
        expected = fixture["expected_substrings"]
        probes.append(
            {
                "name": name,
                "prompt": fixture["prompt"],
                "expected_answer": fixture["expected_answer"],
                "expected_substrings": expected,
                "semantic_labels": fixture.get("semantic_labels", []),
                "event_timing_ms": fixture.get("event_timing_ms", {}),
                "raw_request_metadata": request_metadata,
                "raw_model_answer": answer,
                "pass": normalize_pass(answer, expected, name),
                "event_response_latency_ms": latency_ms if fixture.get("event_timing_ms") else None,
            }
        )
        print(json.dumps({"fixture": name, "latency_ms": latency_ms, "answer": answer}, ensure_ascii=False))

    statuses: dict[str, Any] = {}
    all_pass = True
    probe_by_name = {probe["name"]: probe for probe in probes}
    for fixture_name, alias in REQUIRED_PROBES.items():
        probe = probe_by_name.get(fixture_name)
        passed = bool(probe and probe.get("pass") is True)
        latency_ok = True
        if fixture_name == "cross_modal_event" and probe:
            latency = probe.get("event_response_latency_ms")
            latency_ok = isinstance(latency, int | float) and latency <= 2000
            statuses["event_response_ms"] = latency
        statuses[alias] = "PASS" if passed and latency_ok else "FAIL"
        all_pass = all_pass and passed and latency_ok

    summary = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine": "Transformers + qwen-omni-utils local inference",
        "model": MODEL_ID,
        "primary_model": PRIMARY_MODEL_ID,
        "candidate_substitution": {
            "used": True,
            "reason": "Primary 7B GPTQ model was accessible and downloaded, but local GPTQ dependencies failed before model initialization; Task 2 explicitly allowed a 3B Qwen Omni short-clip path as a plausible same-family local route.",
        },
        "snapshot": str(SNAPSHOT),
        "fixture_manifest": str(FIXTURES_DIR / "manifest.json"),
        "probe_count": len(probes),
        "all_required_present": set(REQUIRED_PROBES) <= {probe["name"] for probe in probes},
        "native_media_direct": True,
        "transcript_text_used": False,
        "remote_inference_used": False,
        "model_load_elapsed_ms": load_elapsed_ms,
        "probes": probes,
        "sequence_summary": {
            "selected_model": "qwen2.5-omni-3b" if all_pass else None,
            "model": MODEL_ID,
            "primary_model": PRIMARY_MODEL_ID,
            "required_statuses": statuses,
            "all_required_passed": all_pass,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(OUT), "all_required_passed": all_pass}, ensure_ascii=False))


if __name__ == "__main__":
    main()
