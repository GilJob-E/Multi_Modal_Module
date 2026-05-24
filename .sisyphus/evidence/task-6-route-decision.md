# Task 6 Native Route Decision

Generated: 2026-05-22T06:04:08Z

Final decision: `native-no-go`.
Native route status: `no-go`.
Fallback enabled: `true` for Task 10 degraded local ASR contingency only.

ASR fallback is degraded and non-native. It is not native success and must not be counted as a native multimodal audio/video pass.

## Fixed Priority Decision

1. Gemma4 E4B passed? No. Evidence: `.sisyphus/evidence/task-4-gemma4-native-probe.json` and `.sisyphus/evidence/task-4-gemma4-no-go.md` show `google/gemma-4-E4B-it` reached `/v1/models` on vLLM, then all six explicit `input_audio` base64 WAV probes failed with HTTP 400 `Invalid or unsupported audio file`.
2. Gemma4 E2B passed? No. Evidence: `.sisyphus/evidence/task-4-gemma4-native-probe.json` and `.sisyphus/evidence/task-4-gemma4-no-go.md` show `google/gemma-4-E2B-it` reached `/v1/models` on vLLM, then all six explicit `input_audio` base64 WAV probes failed with HTTP 400 `Invalid or unsupported audio file`.
3. Qwen native passed? No. Evidence: `.sisyphus/evidence/task-5-qwen-native-probe.json` and `.sisyphus/evidence/task-5-qwen-no-go.md` show primary `Qwen/Qwen2.5-Omni-7B-GPTQ-Int4` failed local GPTQ load due missing `optimum`, while alternate `Qwen/Qwen2.5-Omni-3B` ran locally with direct WAV audio plus muted MP4 video but had `sequence_summary.all_required_passed=false`.
4. Therefore select `native-no-go` and enable degraded local ASR fallback only as a non-native contingency.

## Evidence References

- `.sisyphus/evidence/task-4-gemma4-native-probe.json`
- `.sisyphus/evidence/task-4-gemma4-no-go.md`
- `.sisyphus/evidence/task-5-qwen-native-probe.json`
- `.sisyphus/evidence/task-5-qwen-no-go.md`

Supporting startup log: `.sisyphus/evidence/task-4-gemma4-vllm-startup.log`.

## Failed Native Routes

### Gemma4 E4B

- Model: `google/gemma-4-E4B-it`
- Engine: `vLLM OpenAI-compatible server, vllm/vllm-openai:nightly`
- Port: `127.0.0.1:8002 -> container 8000`
- Launch command: `docker run -d --name vllm-gemma4-e4b-task4-port8002 --gpus all --ipc=host --shm-size 16G -p 127.0.0.1:8002:8000 -v /home/kio/hf_cache:/root/.cache/huggingface -v /home/kio/workspace/gje:/workspace/gje:ro -e VLLM_ENGINE_READY_TIMEOUT_S=3600 -e HF_TOKEN=<HF_TOKEN_REDACTED> vllm/vllm-openai:nightly --host 0.0.0.0 --port 8000 --model google/gemma-4-E4B-it --tensor-parallel-size 1 --max-model-len 4096 --max-num-batched-tokens 8192 --gpu-memory-utilization 0.90 --limit-mm-per-prompt {"video":1,"audio":1,"image":4} --allowed-local-media-path /workspace/gje --dtype bfloat16`
- Payload shape: OpenAI-compatible multimodal request using explicit `input_audio` base64 WAV payloads with text prompts; startup allowed `video`, `audio`, and `image` media.
- Probe scores: `english_passphrase=FAIL`, `korean_passphrase=FAIL`, `no_audio_ablation=FAIL`, `beep_only=FAIL`, `av_sync=FAIL`, `cross_modal_event=FAIL`, `event_response_ms=14.3`, `all_required_passed=false`.
- Failure: readiness was not the final blocker; `/v1/models` returned HTTP 200, but explicit WAV audio probes were rejected as unsupported with HTTP 400.

### Gemma4 E2B

- Model: `google/gemma-4-E2B-it`
- Engine: `vLLM OpenAI-compatible server, vllm/vllm-openai:nightly`
- Port: `127.0.0.1:8002 -> container 8000`
- Launch command: `docker run -d --name vllm-gemma4-e2b-task4-port8002 --gpus all --ipc=host --shm-size 16G -p 127.0.0.1:8002:8000 -v /home/kio/hf_cache:/root/.cache/huggingface -v /home/kio/workspace/gje:/workspace/gje:ro -e VLLM_ENGINE_READY_TIMEOUT_S=3600 -e HF_TOKEN=<HF_TOKEN_REDACTED> vllm/vllm-openai:nightly --host 0.0.0.0 --port 8000 --model google/gemma-4-E2B-it --tensor-parallel-size 1 --max-model-len 4096 --max-num-batched-tokens 8192 --gpu-memory-utilization 0.90 --limit-mm-per-prompt {"video":1,"audio":1,"image":4} --allowed-local-media-path /workspace/gje --dtype bfloat16`
- Payload shape: OpenAI-compatible multimodal request using explicit `input_audio` base64 WAV payloads with text prompts; startup allowed `video`, `audio`, and `image` media.
- Probe scores: `english_passphrase=FAIL`, `korean_passphrase=FAIL`, `no_audio_ablation=FAIL`, `beep_only=FAIL`, `av_sync=FAIL`, `cross_modal_event=FAIL`, `event_response_ms=15.0`, `all_required_passed=false`.
- Failure: readiness was not the final blocker; `/v1/models` returned HTTP 200, but explicit WAV audio probes were rejected as unsupported with HTTP 400.

### Qwen2.5-Omni Primary GPTQ

- Model: `Qwen/Qwen2.5-Omni-7B-GPTQ-Int4`
- Engine: `Transformers + qwen-omni-utils local offline inference`
- Port: none; local library route, no server.
- Launch command: `uv run --offline --with torch --with torchvision --with transformers --with qwen-omni-utils --with accelerate --with decord python local-infer/tools/probe_qwen_omni_native.py --fixtures .sisyphus/evidence/audio-fixtures --out .sisyphus/evidence/task-5-qwen-native-probe.json`
- Payload shape: intended Qwen typed content list with direct `audio`, `video`, and `text`; no transcript text and no remote inference.
- Probe scores: none, because model initialization failed before inference.
- Failure: cached primary GPTQ snapshot existed, but local initialization failed with `ImportError: Loading a GPTQ quantized model requires optimum (`pip install optimum`)`.

### Qwen2.5-Omni 3B Alternate

- Model: `Qwen/Qwen2.5-Omni-3B`
- Engine: `Transformers + qwen-omni-utils local offline inference`
- Port: none; local library route, no server.
- Launch command: `uv run --offline --with torch --with torchvision --with transformers --with qwen-omni-utils --with accelerate --with decord python local-infer/tools/probe_qwen_omni_native.py --fixtures .sisyphus/evidence/audio-fixtures --out .sisyphus/evidence/task-5-qwen-native-probe.json`
- Payload shape: Qwen typed content list containing explicit WAV `audio` local path, muted MP4 `video` local path, and prompt text; `transcript_text_used=false`, `remote_inference_used=false`, `use_audio_in_video=false`.
- Probe scores: `audio_positive=FAIL`, `no_audio_ablation=FAIL`, `beep_only=PASS`, `korean_phrase=FAIL`, `av_sync=PASS`, `cross_modal_event=PASS`, `event_response_ms=1113.692`, `event_response_budget_ms=2000`, `all_required_passed=false`, `selected_model=null`.
- Failure: cross-modal event passed within budget, but Qwen must not be selected because the required audio-positive, no-audio ablation, and Korean phrase checks failed.

## Outcome

No native route passed. The selected route is `native-no-go`, `native_route_status` is `no-go`, and `fallback_enabled` is `true`.

The fallback is degraded local ASR contingency only. It is not native multimodal audio/video understanding success, and downstream work must not treat ASR fallback as native success.
