# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`gje` (GilJob) is a workspace for a real-time multimodal interview system. The single shipped deliverable is `local-infer/`: a **low-latency, video-native local inference gateway** that fronts a vLLM server running `google/gemma-4-31B-it` (online fp8, TP=2 on 2×4090). It is a FastAPI app exposing OpenAI-compatible SSE streaming. Everything else (`sglang/`, `video-test/`) is experiment/benchmark history; `.sisyphus/` and `.hermes/` hold planning and evidence records.

Most documentation and code comments are in Korean. This is intentional — match the surrounding language when editing docs.

## Commands

All commands run from `local-infer/`. The project uses `uv` and requires `PYTHONPATH=src`.

```bash
# Full test suite
PYTHONPATH=src uv run --with pytest --with httpx pytest tests -q

# Single test file / single test
PYTHONPATH=src uv run --with pytest --with httpx pytest tests/test_native_app.py -q
PYTHONPATH=src uv run --with pytest --with httpx pytest tests/test_native_app.py::<test_name> -q

# Native-path targeted tests (the refactor's Definition of Done set)
PYTHONPATH=src uv run --with pytest --with httpx pytest \
  tests/test_native_media_store.py tests/test_native_audio.py \
  tests/test_native_payloads.py tests/test_native_app.py \
  tests/test_native_forbidden_paths.py -q

# Run the server (needs a reachable vLLM at VLLM_BASE_URL)
PYTHONPATH=src VLLM_BASE_URL=http://localhost:8000 uvicorn local_infer.app:app --host 0.0.0.0 --port 8080

# Structural smoke (no GPU needed; uses an in-process fake vLLM). Run from repo root.
python3 local-infer/tools/smoke_vid0033_native_stream.py \
  --source /home/kio/workspace/gje/vid_0033.mp4 \
  --out .sisyphus/evidence/native-streaming-vid0033-smoke.json \
  --in-process-fake-vllm --session-id native-smoke-vid0033
```

Tests use a fake vLLM and do not need a GPU. The `tools/probe_*.py` scripts do hit a real vLLM/GPU.

### GPU operating rule (non-negotiable)

When the model is not in use, stop the container and confirm VRAM is released — both GPUs should read single-digit MiB, 0% util.

```bash
docker stop vllm-gemma4
nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader
```

## Architecture

The gateway keeps **three strictly separate request flows**. Conflating them is the most common mistake — see the proof-gate invariant below.

1. **Frame-only visual baseline** (original low-latency path)
   - `POST /v1/sessions/{id}/frames` pushes JPEG frames into a per-session bounded buffer (`FrameStore`).
   - `POST /v1/sessions/{id}/generate` sends the most recent N frames as `image_url[]` to vLLM and streams SSE back.
   - This is a *visual* baseline for the 31B model, **not** audio understanding.

2. **Native user-override path** (added MP4+audio path)
   - `POST /v1/native/sessions/{id}/windows` stores a rolling base64 MP4 window file (`NativeMediaStore`).
   - `POST /v1/native/sessions/{id}/generate` extracts WAV from the *same* stored window (`NativeAudioExtractor`) and sends a `video_url` + `input_audio` (+ text) payload — **never `image_url[]`**.
   - The audio is same-window transport, not ASR/VAD/transcript.

3. **Degraded local audio-analysis fallback**
   - `POST /v1/sessions/{id}/audio` stores WAV chunks (`AudioStore`).
   - `POST /v1/sessions/{id}/generate-av-fallback` does deterministic local cue analysis + frame presence and emits `native_success=false`, `fallback_mode=degraded_local_audio_analysis`. This is **not** native inference.

### Source map (`src/local_infer/`)

- `app.py` — FastAPI app + all endpoints + SSE event generation (`ttft`/`token`/`final`)
- `frame_store.py` / `audio_store.py` — per-session bounded in-memory buffers
- `payloads.py` — builds `image_url[]` chat payload (frame path)
- `native_media_store.py` — bounded MP4 window file store; produces `video_url` from `LOCAL_INFER_NATIVE_MEDIA_URL_PREFIX`
- `native_audio.py` — same-window WAV `input_audio` extraction
- `native_payloads.py` — builds `video_url` + `input_audio` + text payload (native path)
- `audio_analysis.py` — deterministic WAV cue analysis (fallback path only)
- `vllm_client.py` — calls vLLM `/v1/models` and `/v1/chat/completions` (stream)
- `vllm_stream.py` — extracts content deltas from vLLM's SSE byte stream

### Environment variables

- `VLLM_BASE_URL` (default `http://localhost:8000`) — upstream vLLM
- `LOCAL_INFER_MODEL` (default `google/gemma-4-31B-it`)
- `LOCAL_INFER_NATIVE_MEDIA_DIR` (default `/tmp/gje-local-infer-native-media`) — where MP4 windows are written
- `LOCAL_INFER_NATIVE_MEDIA_URL_PREFIX` (default `file://{NATIVE_MEDIA_DIR}`) — the prefix used to build `video_url`. When vLLM runs in Docker, the media dir must be mounted into the container at a path matching this prefix, or vLLM cannot read the file.

## The proof-gate invariant (read before changing docs/tests/claims)

This project maintains an audit trail in `.sisyphus/evidence/`. The canonical state is **native audio is NO-GO**, and the documentation deliberately preserves that. Do not "fix" docs to claim success.

- Canonical gate: `.sisyphus/evidence/vid0033-native-proof-gate.json` → `gemma4_capability_no_go`, `streaming_refactor_allowed=false`. The fixed real fixture is `/home/kio/workspace/gje/vid_0033.mp4`. **Never flip this to pass.**
- Route lock: `.sisyphus/evidence/task-6-route-decision.json` → `selected_route=native-no-go`, `fallback_enabled=true`. Gemma4 E4B/E2B and Qwen2.5-Omni native audio probes both failed (Tasks 4–5); Tasks 7–8 were blocked/skipped, so there is no `/generate-av-native` endpoint.
- The native MP4 path (flow 2) exists only because of an explicit **user override**: `.sisyphus/evidence/native-streaming-user-override-go.json` → `user_override_capability_go_for_refactor`. This authorizes the engineering refactor; it does **not** retroactively pass the proof gate or claim native audio understanding.

When editing any doc (README.md, INFERENCE_PIPELINE.md, local-infer/README.md, local-infer/docs/*), hold these phrasings true: the fallback path is not native success, fallback paths are not native proof, and `audio_analysis` is not native media understanding. Keep the no-go evidence visible rather than deleting it.

## Further reading

- `INFERENCE_PIPELINE.md` — top-level index of results and file locations
- `local-infer/docs/{ARCHITECTURE,API_CONTRACT,RUNBOOK,DECISIONS}.md`
- `sglang/EXPERIMENT_LOG.md` — why SGLang was rejected (vLLM was adopted)
