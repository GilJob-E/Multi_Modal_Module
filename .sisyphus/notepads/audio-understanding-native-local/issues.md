
- Plain `pytest` is not installed globally here, so the documented `env PYTHONPATH=src uv run --with pytest --with httpx pytest tests -q` fallback was required for verification.
- Task 3: Plain `pytest` is not installed on PATH in this environment; related tests passed via `uv run --project . --with pytest pytest ...`.

- 2026-05-22T05:25:28.776042+00:00 Task 4 Gemma4 vLLM probe: both `google/gemma-4-E4B-it` and `google/gemma-4-E2B-it` started on isolated port 8002 with `/v1/models` ready, but all six explicit `input_audio` base64 WAV probes returned HTTP 400 `Invalid or unsupported audio file`; both task containers were stopped and removed. Evidence: `.sisyphus/evidence/task-4-gemma4-native-probe.json`, `.sisyphus/evidence/task-4-gemma4-no-go.md`, `.sisyphus/evidence/task-4-gemma4-vllm-startup.log`.

- 2026-05-22T05:30:11.164673+00:00 Task 5 Qwen2.5-Omni probe: Qwen branch was active because Task 4 JSON status is `NO_GO`, but no local Qwen native AV route could be run. `/home/kio/hf_cache/hub` has no Qwen/Omni checkpoint, no HF token file is present, host Python lacks torch/transformers/qwen_omni_utils/decord/accelerate/quantization modules, and port 8003 was closed. Evidence: `.sisyphus/evidence/task-5-qwen-no-go.md`.

- 2026-05-22T05:37:20.525256+00:00 Task 5 corrected Qwen probe: `/home/kio/hf_cache/qwen-hub` did contain cached Qwen2.5-Omni snapshots, so a local Transformers + qwen-omni-utils probe was run with direct WAV audio plus muted MP4 video. Primary `Qwen/Qwen2.5-Omni-7B-GPTQ-Int4` remained no-go due missing local `optimum` GPTQ runtime; alternate `Qwen/Qwen2.5-Omni-3B` loaded and probed but failed required audio-positive, no-audio ablation, and Korean phrase checks. Evidence: `.sisyphus/evidence/task-5-qwen-native-probe.json` and `.sisyphus/evidence/task-5-qwen-no-go.md`.

- 2026-05-22T06:04:08Z Task 6 route lock: fixed priority order selected `native-no-go` because Gemma4 E4B and E2B both reached vLLM readiness but rejected explicit `input_audio` WAV probes, and Qwen2.5-Omni did not pass all required local native probes. Degraded local ASR is enabled only as non-native fallback evidence, not native success. Evidence: `.sisyphus/evidence/task-6-route-decision.json` and `.sisyphus/evidence/task-6-route-decision.md`.

- 2026-05-22T06:20:00Z Task 8 blocked/skipped native integration tests: no selected native route exists after Task 6 `native-no-go`, and `.sisyphus/evidence/task-7-blocked.md` was not present. Existing `local-infer` regression suite passed with 57 tests. Evidence: `.sisyphus/evidence/task-8-blocked.md` and `.sisyphus/evidence/task-8-test-summary.txt`.

- 2026-05-22T00:00:00Z Task 7 blocked: no explicit native audio path was added because Task 6 selected `native-no-go`; `/generate-av-native` would imply a passing native route. Degraded local ASR remains non-native Task 10 contingency only. Evidence: `.sisyphus/evidence/task-7-blocked.md`.
