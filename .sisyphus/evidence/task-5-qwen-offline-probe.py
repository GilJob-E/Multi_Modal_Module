#!/usr/bin/env python3
# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportAny=false, reportUnusedImport=false
from __future__ import annotations

import json
import os
from pathlib import Path

from huggingface_hub import scan_cache_dir
from transformers import AutoProcessor
from qwen_omni_utils import process_mm_info  # noqa: F401 - import proves Qwen native media utility availability

MODEL_ID = "Qwen/Qwen2.5-Omni-7B-GPTQ-Int4"
FIXTURES_DIR = Path(".sisyphus/evidence/audio-fixtures")
HF_CACHE = "/home/kio/hf_cache"

os.environ["HF_HOME"] = HF_CACHE
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

manifest = json.loads((FIXTURES_DIR / "manifest.json").read_text(encoding="utf-8"))
cache = scan_cache_dir(f"{HF_CACHE}/hub")
repo_ids = sorted(repo.repo_id for repo in cache.repos)

messages = []
for fixture in manifest["fixtures"].values():
    content = [
        {"type": "audio", "audio": str(FIXTURES_DIR / fixture["media"]["audio_wav"]["path"])}
    ]
    for frame in fixture["media"].get("frames_jpeg", []):
        content.append({"type": "image", "image": str(FIXTURES_DIR / frame["path"])})
    content.append({"type": "text", "text": fixture["prompt"]})
    messages.append({"role": "user", "content": content})

print(json.dumps({
    "engine": "Transformers + qwen-omni-utils",
    "model_id": MODEL_ID,
    "fixtures": len(manifest["fixtures"]),
    "route": "offline local_files_only typed Qwen audio/image/text messages",
    "cache_repos": repo_ids,
    "model_cached": MODEL_ID in repo_ids,
    "first_message_content_types": [part["type"] for part in messages[0]["content"]],
}, ensure_ascii=False, indent=2))

try:
    processor = AutoProcessor.from_pretrained(MODEL_ID, local_files_only=True, trust_remote_code=True)
except Exception as exc:
    print(json.dumps({
        "processor_load_error_type": exc.__class__.__name__,
        "processor_load_error": str(exc),
    }, ensure_ascii=False, indent=2))
    raise

print(json.dumps({"processor_loaded": processor.__class__.__name__}, ensure_ascii=False))
