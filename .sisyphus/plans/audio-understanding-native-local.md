# Local Native Audio Understanding for GilJob

## TL;DR
> **Summary**: Replace the false assumption that current `google/gemma-4-31B-it` `video_url` uses MP4 audio with a proven local-GPU native audio path. Primary route is vLLM + Gemma4 E4B/E2B explicit audio input; Qwen2.5-Omni is the native fallback; local ASR is contingency only after native no-go evidence.
> **Deliverables**:
> - Local-only native audio probe harness with controlled fixtures and ablation evidence.
> - Deterministic model/engine selection record: Gemma4 E4B → Gemma4 E2B → Qwen2.5-Omni → degraded ASR contingency.
> - `local-infer` API extension for explicit audio-window + recent-frame native generation.
> - Tests, runbook updates, evidence package proving audio-token ingestion.
> **Effort**: Large
> **Parallel**: YES - 4 waves
> **Critical Path**: Task 1 → Task 2/3 → Task 4/5 → Task 6 → Task 7/8/9

## Context
### Original Request
User asked: `/goal 오디오이해되는 상태 만들어와. 다른 모델이든 엔진이든 아니면 작은 변경이든 알아서 잘, 현업 AI ops 전문가 답게 해와`.

### Interview Summary
- Project target is **video+audio native 실시간 면접 모델**, **오디오까지 분석하는 멀티모달 면접관**, **비디오 스트림을 네이티브로 이해하는 시스템**.
- Practical product target: if the user configures an instruction like "내가 하늘을 보면서 아~ 라고 목소리를 내면 반응해", the live system should detect the **combined visual cue** (looking at the sky) plus **vocal cue** ("아~") and respond within about **2 seconds**. This is cross-modal real-time event detection/response; strict continuous `video_url` ingestion is not required for the first working path.
- Current JPEG frame path is an interim MVP, not the final product framing.
- User selected **Native 우선**: single native audio/video model path before ASR fusion.
- User selected **로컬 GPU만**: no cloud/managed model as success path.
- Live probe already showed current `google/gemma-4-31B-it` on vLLM did not use AAC audio from MP4 `video_url`.

### Metis Review (gaps addressed)
- Guardrail: do not count MP4 upload success as audio understanding.
- Guardrail: do not let ASR+vision fusion redefine native success.
- Guardrail: preserve current 31B frame/vision baseline while probing audio-capable candidates.
- Required tests: audio-positive, no-audio ablation, beep-only, Korean phrase, audio-video sync, cross-modal event response under 2 seconds, local-only, baseline regression.

## Work Objectives
### Core Objective
Make audio understanding work in a **local-GPU, native-first** way and prove it through controlled ablation before app integration.

The execution should optimize toward the practical event target: detect a visual cue plus vocal cue during live interaction and produce a response inside a 2-second budget after the event is observable.

### Deliverables
- Native local audio-capable model/engine route selected with evidence.
- Audio/video fixture generator and probe runner.
- Cross-modal event probe covering "look at sky" + "아~"-style vocal cue and measuring response timing budget.
- `local-infer` explicit audio input path using `input_audio`/`audio_url`, not hidden MP4 audio.
- Unit and integration tests proving audio payload construction and native model response behavior.
- Runbook/API/decision docs updated to distinguish native audio path from frame-only baseline and ASR fallback.

### Definition of Done (verifiable conditions with commands)
- `cd /home/kio/workspace/gje/local-infer && PYTHONPATH=src pytest tests -q` passes.
- `python3 local-infer/tools/make_av_fixtures.py --out .sisyphus/evidence/audio-fixtures` creates deterministic local fixtures without manual listening.
- `python3 local-infer/tools/probe_native_audio.py --base-url http://localhost:8002 --fixtures .sisyphus/evidence/audio-fixtures --out .sisyphus/evidence/native-audio-probe.json` reports `audio_positive=PASS`, `no_audio_ablation=PASS`, `beep_only=PASS`, `korean_phrase=PASS`, `av_sync=PASS` for the selected native route.
- The same probe output includes `cross_modal_event=PASS` and `event_response_ms <= 2000` for the "look at sky + 아~" style fixture, or records a correctness-pass/latency-fail split if model correctness works but latency is not yet within budget.
- `python3 local-infer/tools/probe_native_audio.py --base-url http://localhost:8000 --model google/gemma-4-31B-it --expect-no-audio --out .sisyphus/evidence/31b-audio-negative.json` preserves evidence that current 31B route is not the native audio path.
- `python3 video-test/bench_nframe.py video-test/frames http://localhost:8000` or documented equivalent confirms frame-only baseline remains operational.

### Must Have
- Native-first route attempted in this exact order: Gemma4 E4B on vLLM, Gemma4 E2B on vLLM, Qwen2.5-Omni native probe, local ASR contingency only after native no-go evidence.
- Explicit audio input (`input_audio` WAV/base64 or `audio_url` WAV), not relying on AAC audio embedded inside MP4 `video_url`.
- Local-only verification: no cloud model APIs, no hosted transcription, no manual listening.
- Evidence files under `.sisyphus/evidence/` for every probe.

### Must NOT Have (guardrails, AI slop patterns, scope boundaries)
- Must not claim `video_url` equals audio understanding.
- Must not present ASR transcript fusion as satisfying native success.
- Must not remove or regress current `/v1/sessions/{id}/frames` + `/generate` visual path.
- Must not start latency optimization before correctness probes pass.
- Must not use cloud APIs as part of the success path.

## Verification Strategy
> ZERO HUMAN INTERVENTION - all verification is agent-executed.
- Test decision: tests-after + gated integration. Atomic native model probes first, then code integration tests.
- QA policy: Every task has agent-executed scenarios.
- Evidence: `.sisyphus/evidence/task-{N}-{slug}.{ext}`

## Execution Strategy
### Parallel Execution Waves
> Target: 5-8 tasks per wave. <3 per wave (except final) = under-splitting.
> Extract shared dependencies as Wave-1 tasks for max parallelism.

Wave 1: Task 1 (baseline/local guard), Task 2 (model support matrix), Task 3 (fixture/probe harness)
Wave 2: Task 4 (Gemma4 E4B/E2B vLLM probes); Task 5 only if Task 4 records Gemma no-go, otherwise write cancellation evidence
Wave 3: Task 6 route lock first, then Task 7 local-infer native audio API, then Task 8 tests/regression
Wave 4: Task 9 (docs/runbook/evidence), Task 10 (contingency gate if all native routes fail)

### Dependency Matrix (full, all tasks)
- Task 1: blocks Tasks 4, 5, 8, 9
- Task 2: blocks Tasks 4, 5, 6
- Task 3: blocks Tasks 4, 5, 8
- Task 4: blocks Task 5 and Task 6
- Task 5: blocks Task 6 only when Task 4 failed; if Task 4 passed, Task 5 must produce cancellation evidence before Task 6
- Task 6: blocks Tasks 7, 9, 10
- Task 7: blocks Task 8
- Task 8: blocks Task 9
- Task 9: blocks final verification
- Task 10: only runs if Task 6 records no native route passed

### Agent Dispatch Summary (wave → task count → categories)
- Wave 1 → 3 tasks → quick, deep, unspecified-high
- Wave 2 → 1 required task + 1 gated fallback task → unspecified-high, deep
- Wave 3 → 3 tasks → deep, unspecified-high, unspecified-high
- Wave 4 → 2 tasks → writing, deep

## TODOs
> Implementation + Test = ONE task. Never separate.
> EVERY task MUST have: Agent Profile + Parallelization + QA Scenarios.

- [x] 1. Capture Local Baseline and Safety Guard

  **What to do**: Record the current hardware/runtime baseline, prove the existing 31B visual path is only a visual baseline, and add local-only guard checks to the probe workflow. Create evidence directory `.sisyphus/evidence/` if absent. Capture `nvidia-smi`, Docker container status for `vllm-gemma4`, current `local-infer` unit test result, and existing negative audio evidence for 31B. Do not modify product code in this task except optional test helper scripts under `local-infer/tools/` if needed for evidence capture.
  **Must NOT do**: Do not start model downloads. Do not change vLLM launch config. Do not claim audio success from MP4 upload.

  **Recommended Agent Profile**:
  - Category: `quick` - Reason: baseline capture and command verification are bounded.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`mem0`] - No memory SDK work.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: [4, 5, 8, 9] | Blocked By: []

  **References** (executor has NO interview context - be exhaustive):
  - Pattern: `local-infer/README.md:95-102` - existing unit test command and current pass count statement.
  - Pattern: `local-infer/docs/RUNBOOK.md:31-38` - test command and expected baseline test flow.
  - Pattern: `local-infer/docs/RUNBOOK.md:47-58` - GPU unload verification convention.
  - Pattern: `sglang/launch-configs/vllm_baseline.sh:16-23` - current 31B vLLM baseline launch options.
  - Pattern: `video-test/infer_ttft.py:12-32` - existing `video_url` benchmark payload.
  - Research finding: current live probe showed AAC MP4 audio was not understood by 31B; preserve that as negative baseline.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `.sisyphus/evidence/task-1-baseline.txt` contains GPU inventory, Docker container state, and local-only note.
  - [ ] `.sisyphus/evidence/task-1-pytest.txt` contains output of `cd /home/kio/workspace/gje/local-infer && PYTHONPATH=src pytest tests -q`.
  - [ ] `.sisyphus/evidence/task-1-31b-negative.json` exists or is referenced from the prior live probe and states that `google/gemma-4-31B-it` is not accepted as audio-native success.
  - [ ] If vLLM is started for baseline verification, it is stopped afterward and `.sisyphus/evidence/task-1-gpu-after-stop.txt` shows GPU memory returned to idle pattern.

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: Baseline test suite still passes
    Tool: Bash
    Steps: cd /home/kio/workspace/gje/local-infer && PYTHONPATH=src pytest tests -q | tee ../.sisyphus/evidence/task-1-pytest.txt
    Expected: command exits 0 and output contains tests passing, not import errors.
    Evidence: .sisyphus/evidence/task-1-pytest.txt

  Scenario: Local-only guard recorded
    Tool: Bash
    Steps: nvidia-smi --query-gpu=index,name,memory.total,memory.used,utilization.gpu --format=csv,noheader | tee .sisyphus/evidence/task-1-baseline.txt
    Expected: evidence contains local GPU rows; no cloud API keys or hosted model endpoints are required for baseline capture.
    Evidence: .sisyphus/evidence/task-1-baseline.txt
  ```

  **Commit**: NO | Message: `ops(audio): capture local baseline` | Files: [.sisyphus/evidence/*]

- [x] 2. Build Native Model and Engine Support Matrix

  **What to do**: Create a deterministic support matrix for local native audio candidates. Verify exact model IDs, licenses/access requirements, vLLM/SGLang/Transformers support, expected VRAM, API shape, and go/no-go conditions. Candidate order is fixed: `google/gemma-4-E4B-it` first, `google/gemma-4-E2B-it` second, Qwen2.5-Omni native route third. Record whether each supports explicit `input_audio`/`audio_url` plus image/video inputs locally. Output a machine-readable matrix and a short decision note.
  **Must NOT do**: Do not use cloud-hosted inference. Do not choose ASR as primary. Do not benchmark before model IDs/API shapes are verified.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: model/engine support is a multi-source architecture decision.
  - Skills: [] - No project skill required.
  - Omitted: [`mem0`] - No persistent memory coding.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: [4, 5, 6] | Blocked By: []

  **References**:
  - External: `https://ai.google.dev/gemma/docs/core/model_card_4` - Gemma4 capability/model-family reference.
  - External: `https://ai.google.dev/gemma/docs/capabilities/audio` - Gemma audio input guidance.
  - External: `https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html` - vLLM Gemma4 serving recipe.
  - External: `https://github.com/vllm-project/vllm/blob/main/vllm/model_executor/models/gemma4_mm.py` - vLLM Gemma4 multimodal implementation; check audio config behavior.
  - External: `https://github.com/QwenLM/Qwen2.5-Omni/blob/main/README.md` - Qwen2.5-Omni native AV candidate.
  - Pattern: `sglang/EXPERIMENT_LOG.md:56-58` - prior SGLang re-evaluation triggers and hardware caveats.

  **Acceptance Criteria**:
  - [ ] `.sisyphus/evidence/task-2-support-matrix.json` contains entries for Gemma4 E4B, Gemma4 E2B, Qwen2.5-Omni, and local ASR contingency with fields: `model_id`, `engine`, `native_audio`, `native_video_or_image`, `local_gpu_fit_assumption`, `api_shape`, `go_condition`, `no_go_condition`.
  - [ ] `.sisyphus/evidence/task-2-decision.md` states the primary attempt order and why 31B is excluded from native audio success.
  - [ ] Matrix explicitly says ASR sidecar is `fallback_only=true`.

  **QA Scenarios**:
  ```
  Scenario: Matrix validates required candidates
    Tool: Bash
    Steps: python3 - <<'PY'
import json
p='.sisyphus/evidence/task-2-support-matrix.json'
d=json.load(open(p))
names={x['name'] for x in d['candidates']}
assert {'gemma4-e4b','gemma4-e2b','qwen2.5-omni','local-asr-contingency'} <= names
assert next(x for x in d['candidates'] if x['name']=='local-asr-contingency')['fallback_only'] is True
PY
    Expected: command exits 0.
    Evidence: .sisyphus/evidence/task-2-support-matrix.json

  Scenario: 31B excluded as native audio success
    Tool: Bash
    Steps: grep -E "31B.*not.*audio|31B.*excluded|audio_config" .sisyphus/evidence/task-2-decision.md
    Expected: command exits 0 and decision note explicitly excludes current 31B route from native audio success.
    Evidence: .sisyphus/evidence/task-2-decision.md
  ```

  **Commit**: NO | Message: `docs(audio): record native support matrix` | Files: [.sisyphus/evidence/task-2-*]

- [x] 3. Create Deterministic Audio/Video Probe Fixtures and Harness

  **What to do**: Add probe tooling under `local-infer/tools/`: `make_av_fixtures.py` and `probe_native_audio.py`. Fixtures must include: English spoken passphrase, Korean spoken passphrase, no-audio same-video ablation, beep-only audio, audio-video sync clip, and a practical cross-modal event fixture approximating "look at sky + 아~" with expected response under a 2-second budget. Generate or fetch only local/offline test assets; if local TTS is unavailable, install/use a local TTS binary or package as a fixture generator, not a cloud TTS service. The probe harness must send explicit audio input (`input_audio` base64 WAV preferred; `audio_url` WAV acceptable) plus optional recent JPEG frames. It must output JSON with pass/fail, event timing, and raw model responses.
  **Must NOT do**: Do not require manual listening. Do not use hosted TTS or hosted ASR. Do not rely on AAC inside MP4 as the only audio input.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: involves test asset generation, payload construction, and robust JSON evidence.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`frontend-ui-ux`] - No UI work.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: [4, 5, 8] | Blocked By: []

  **References**:
  - Pattern: `video-test/bench_nframe.py:23-45` - existing local fixture loading and multimodal payload pattern.
  - Pattern: `video-test/infer_ttft.py:12-32` - existing OpenAI-compatible multimodal request shape.
  - Pattern: `local-infer/src/local_infer/payloads.py:23-34` - current image parts before text prompt.
  - Pattern: `local-infer/tests/test_frame_store.py:27-45` - deterministic payload unit-test style.
  - Metis requirement: happy/no-audio/beep/Korean/audio-video-sync probes must be machine-verifiable.

  **Acceptance Criteria**:
  - [ ] `local-infer/tools/make_av_fixtures.py` exists and can create fixtures under `.sisyphus/evidence/audio-fixtures/`.
  - [ ] `local-infer/tools/probe_native_audio.py` exists and accepts `--base-url`, `--model`, `--fixtures`, `--out`, and `--expect-no-audio`.
  - [ ] Fixture manifest `.sisyphus/evidence/audio-fixtures/manifest.json` contains expected answers and event timing metadata for every probe.
  - [ ] Probe output JSON contains raw request metadata, raw model answer, normalized pass/fail, event response latency where applicable, and no manual-evaluation fields.

  **QA Scenarios**:
  ```
  Scenario: Fixture generator creates all required fixture metadata
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && python3 local-infer/tools/make_av_fixtures.py --out .sisyphus/evidence/audio-fixtures && python3 - <<'PY'
import json
m=json.load(open('.sisyphus/evidence/audio-fixtures/manifest.json'))
required={'english_passphrase','korean_passphrase','no_audio_ablation','beep_only','av_sync','cross_modal_event'}
assert required <= set(m['fixtures'])
PY
    Expected: command exits 0 and manifest contains all required fixtures, including cross_modal_event with a 2000ms response budget.
    Evidence: .sisyphus/evidence/audio-fixtures/manifest.json

  Scenario: Probe harness dry-run validates fixture expectations
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && python3 local-infer/tools/probe_native_audio.py --fixtures .sisyphus/evidence/audio-fixtures --dry-run --out .sisyphus/evidence/task-3-dry-run.json
    Expected: command exits 0 and JSON contains each probe with expected substrings and payload media types.
    Evidence: .sisyphus/evidence/task-3-dry-run.json
  ```

  **Commit**: NO | Message: `test(audio): add native audio probe harness` | Files: [local-infer/tools/make_av_fixtures.py, local-infer/tools/probe_native_audio.py, .sisyphus/evidence/audio-fixtures/*]

- [x] 4. Probe Gemma4 E4B/E2B Native Audio on vLLM

  **What to do**: Launch a separate local vLLM container/port for Gemma4 E4B first, then Gemma4 E2B only if E4B fails model availability/startup/probe. Use explicit audio multimodal settings and the fixture harness from Task 3. Preferred port: `8002`. Preferred model order: `google/gemma-4-E4B-it`, then `google/gemma-4-E2B-it`. Preferred audio payload: `input_audio` WAV/base64; if vLLM for the selected model only supports `audio_url`, use local `file://` or localhost-served WAV and document the exact API shape. Add `local-infer/tools/probe_gemma4_vllm_sequence.py` to make the E4B→E2B launch/probe/no-go sequence executable as one command. Record startup logs, `/v1/models`, probe outputs, and GPU stats.
  **Must NOT do**: Do not replace existing `vllm-gemma4` container on port 8000. Do not retry indefinitely: max two launch attempts per model (`TP=1` then `TP=2` if OOM). Do not use current 31B as success for this task.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: local model serving, GPU ops, and probe interpretation.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`mem0-cli`] - No CLI memory work.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: [6] | Blocked By: [1, 2, 3]

  **References**:
  - Pattern: `sglang/launch-configs/vllm_baseline.sh:11-23` - current Docker/vLLM launch pattern to adapt without modifying baseline.
  - Pattern: `local-infer/docs/RUNBOOK.md:3-22` - readiness check pattern for `/v1/models`.
  - External: `https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html` - Gemma4 vLLM serving recipe.
  - External: `https://ai.google.dev/gemma/docs/capabilities/audio` - audio-capable Gemma family guidance.
  - Evidence dependency: `.sisyphus/evidence/task-2-support-matrix.json` - verified model IDs and API shape.

  **Acceptance Criteria**:
  - [ ] `local-infer/tools/probe_gemma4_vllm_sequence.py` exists and handles E4B then E2B deterministic launch/probe/no-go recording.
  - [ ] `.sisyphus/evidence/task-4-gemma4-vllm-startup.log` records exact Docker/vLLM commands and readiness result.
  - [ ] `.sisyphus/evidence/task-4-gemma4-native-probe.json` exists and contains pass/fail for all fixture probes.
  - [ ] If E4B passes all required probes, E2B is not launched; record `selected_model=gemma4-e4b`.
  - [ ] If E4B fails, E2B is attempted and E4B no-go reason is written to `.sisyphus/evidence/task-4-gemma4-e4b-no-go.md`.
  - [ ] Any started test container is stopped or left intentionally running only if Task 7 immediately needs it; status is recorded.

  **QA Scenarios**:
  ```
  Scenario: Gemma4 native audio positive and ablation probes
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && python3 local-infer/tools/probe_gemma4_vllm_sequence.py --models google/gemma-4-E4B-it google/gemma-4-E2B-it --port 8002 --fixtures .sisyphus/evidence/audio-fixtures --out .sisyphus/evidence/task-4-gemma4-native-probe.json --no-go-out .sisyphus/evidence/task-4-gemma4-no-go.md --startup-log .sisyphus/evidence/task-4-gemma4-vllm-startup.log
    Expected: final native probe JSON has audio_positive=PASS, no_audio_ablation=PASS, beep_only=PASS, korean_phrase=PASS, av_sync=PASS, cross_modal_event=PASS, and event_response_ms <= 2000, or no-go evidence exists for both E4B and E2B.
    Evidence: .sisyphus/evidence/task-4-gemma4-native-probe.json

  Scenario: Startup failure is captured as deterministic no-go
    Tool: Bash
    Steps: test -f .sisyphus/evidence/task-4-gemma4-native-probe.json || test -f .sisyphus/evidence/task-4-gemma4-no-go.md
    Expected: either passing probe JSON exists or no-go document exists with model, command, error, and next candidate.
    Evidence: .sisyphus/evidence/task-4-gemma4-no-go.md
  ```

  **Commit**: NO | Message: `ops(audio): probe gemma4 native audio` | Files: [.sisyphus/evidence/task-4-*]

- [x] 5. Probe Qwen2.5-Omni Native AV Fallback Locally

  **What to do**: Only if Task 4 fails all Gemma4 native candidates, probe Qwen2.5-Omni or the exact Qwen native AV candidate identified in Task 2. Use the same fixtures and evidence format as Task 4. Prefer the least invasive local serving route documented by Qwen/vLLM for text responses from audio+video inputs. Use a separate port (`8003`) and container/name. Record whether the route supports audio+video jointly or audio-only plus image/video separately.
  **Must NOT do**: Do not skip this task if Gemma4 fails. Do not use remote Qwen API. Do not accept text-only LLM over ASR transcript as native AV fallback.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: alternate model/serving path with higher stack risk.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`mem0-vercel-ai-sdk`] - No Vercel AI SDK work.

  **Parallelization**: Can Parallel: NO; gated fallback after Task 4. If Task 4 passes, do not probe Qwen and write cancellation evidence | Wave 2 | Blocks: [6] | Blocked By: [1, 2, 3, 4]

  **References**:
  - External: `https://github.com/QwenLM/Qwen2.5-Omni/blob/main/README.md` - Qwen2.5-Omni native multimodal reference.
  - External: `https://docs.vllm.ai/en/latest/getting_started/examples/qwen2_5_omni.html` - vLLM Qwen2.5-Omni example.
  - Pattern: `sglang/EXPERIMENT_LOG.md:50-58` - prior lesson: engine/model support must be empirically proven, not assumed.
  - Evidence dependency: `.sisyphus/evidence/audio-fixtures/manifest.json` - required fixture expectations.

  **Acceptance Criteria**:
  - [ ] If Task 4 passed, `.sisyphus/evidence/task-5-cancelled.md` states Qwen probe skipped because Gemma4 native route passed.
  - [ ] If Task 4 failed, `.sisyphus/evidence/task-5-qwen-native-probe.json` contains pass/fail for all fixture probes or `.sisyphus/evidence/task-5-qwen-no-go.md` contains deterministic no-go evidence.
  - [ ] Qwen route is only considered passing if it consumes audio media directly, not transcript text.

  **QA Scenarios**:
  ```
  Scenario: Qwen gated branch is consistent
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && python3 - <<'PY'
import pathlib
gemma_pass=pathlib.Path('.sisyphus/evidence/task-4-gemma4-native-probe.json').exists()
if gemma_pass:
    assert pathlib.Path('.sisyphus/evidence/task-5-cancelled.md').exists()
else:
    assert pathlib.Path('.sisyphus/evidence/task-5-qwen-native-probe.json').exists() or pathlib.Path('.sisyphus/evidence/task-5-qwen-no-go.md').exists()
PY
    Expected: command exits 0 for either valid branch: Gemma pass with Qwen cancellation, or Gemma no-go with Qwen probe/no-go evidence.
    Evidence: .sisyphus/evidence/task-5-cancelled.md or .sisyphus/evidence/task-5-qwen-native-probe.json

  Scenario: Qwen native fallback proves or disproves audio directly
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && if test -f .sisyphus/evidence/task-5-cancelled.md; then exit 0; fi; MODEL=$(python3 -c "import json; d=json.load(open('.sisyphus/evidence/task-2-support-matrix.json')); print(next(c['model_id'] for c in d['candidates'] if c['name']=='qwen2.5-omni'))") && python3 local-infer/tools/probe_native_audio.py --base-url http://localhost:8003 --model "$MODEL" --fixtures .sisyphus/evidence/audio-fixtures --out .sisyphus/evidence/task-5-qwen-native-probe.json || test -f .sisyphus/evidence/task-5-qwen-no-go.md
    Expected: exits 0 when Qwen was correctly cancelled because Gemma passed, or when Qwen probe/no-go evidence exists after Gemma failed.
    Evidence: .sisyphus/evidence/task-5-cancelled.md or .sisyphus/evidence/task-5-qwen-native-probe.json or .sisyphus/evidence/task-5-qwen-no-go.md
  ```

  **Commit**: NO | Message: `ops(audio): probe qwen native av fallback` | Files: [.sisyphus/evidence/task-5-*]

- [x] 6. Lock the Native Route or Trigger Degraded Contingency

  **What to do**: Read Task 4 and Task 5 evidence and produce `.sisyphus/evidence/task-6-route-decision.md` plus `.sisyphus/evidence/task-6-route-decision.json`. Decision algorithm: if Gemma4 E4B passes, select Gemma4 E4B; else if Gemma4 E2B passes, select Gemma4 E2B; else if Qwen native passes, select Qwen route; else mark `native_route=no-go` and enable Task 10 degraded local ASR contingency. The decision must include exact model, engine, port, payload shape, launch command, and probe scores.
  **Must NOT do**: Do not hand-pick based on subjective quality. Do not choose ASR if any native route passed required probes. Do not integrate into app before this decision file exists.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: architecture gate with deterministic route selection.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`frontend-ui-ux`] - No UI work.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: [7, 9, 10] | Blocked By: [4, and either Task 5 completion or Task 5 cancellation evidence]

  **References**:
  - Evidence: `.sisyphus/evidence/task-4-gemma4-native-probe.json` - primary probe result.
  - Evidence: `.sisyphus/evidence/task-5-qwen-native-probe.json` or `.sisyphus/evidence/task-5-cancelled.md` - fallback probe result.
  - Draft decision: `.sisyphus/drafts/audio-understanding.md` - confirmed Native/local constraints.
  - Metis Review: native route and ASR fallback must be separated.

  **Acceptance Criteria**:
  - [ ] `.sisyphus/evidence/task-6-route-decision.json` has `selected_route`, `native_route_status`, `model_id`, `engine`, `payload_shape`, and `fallback_enabled` fields.
  - [ ] If `fallback_enabled=true`, all native no-go files exist and are referenced.
  - [ ] If a native route is selected, `fallback_enabled=false` and Task 10 is marked unnecessary/cancelled by evidence.

  **QA Scenarios**:
  ```
  Scenario: Route decision follows fixed priority order
    Tool: Bash
    Steps: python3 - <<'PY'
import json
d=json.load(open('.sisyphus/evidence/task-6-route-decision.json'))
assert d['selected_route'] in ['gemma4-e4b','gemma4-e2b','qwen2.5-omni','native-no-go']
assert 'payload_shape' in d
if d['selected_route'] != 'native-no-go':
    assert d['fallback_enabled'] is False
PY
    Expected: command exits 0.
    Evidence: .sisyphus/evidence/task-6-route-decision.json

  Scenario: Native failure does not silently become ASR success
    Tool: Bash
    Steps: grep -E 'ASR.*fallback|native.*no-go|not native success' .sisyphus/evidence/task-6-route-decision.md
    Expected: if native failed, decision doc labels ASR as degraded contingency, not native success.
    Evidence: .sisyphus/evidence/task-6-route-decision.md
  ```

  **Commit**: NO | Message: `docs(audio): lock native route decision` | Files: [.sisyphus/evidence/task-6-*]

- [x] 7. Add Explicit Native Audio Path to `local-infer`

  **What to do**: Extend `local-infer` without breaking existing frame-only endpoints. Add an audio buffer and native AV generation endpoint that sends explicit audio media to the selected native route from Task 6. Required API additions: `POST /v1/sessions/{session_id}/audio` with `{timestamp_ms, audio_wav_base64, duration_ms}` and `POST /v1/sessions/{session_id}/generate-av-native` with `{prompt, n_frames, audio_window_ms, max_tokens, temperature}` returning the same SSE event style as current `/generate`, plus `audio_used_ms` and `native_route` in final event. Add payload builder that constructs image parts + explicit audio part + text prompt in the API shape selected by Task 6. Existing `/frames` and `/generate` behavior must remain unchanged.
  **Must NOT do**: Do not overload JPEG `frames` endpoint with audio. Do not rely on MP4 AAC inside `video_url`. Do not remove `DEFAULT_SYSTEM_PROMPT`; create audio-aware default only for native AV endpoint if needed.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: API extension, data model, payload builder, and streaming response changes.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`mem0`] - No memory layer work.

  **Parallelization**: Can Parallel: YES with Task 9 docs draft after Task 6, but final docs depend on implementation | Wave 3 | Blocks: [8] | Blocked By: [6]

  **References**:
  - Pattern: `local-infer/src/local_infer/app.py:19-29` - current Pydantic request models.
  - Pattern: `local-infer/src/local_infer/app.py:54-100` - current frame and generate endpoint style, SSE event style.
  - Pattern: `local-infer/src/local_infer/frame_store.py:15-55` - bounded per-session store pattern to mirror for audio windows.
  - Pattern: `local-infer/src/local_infer/payloads.py:11-57` - current multimodal payload builder to extend or parallelize.
  - Pattern: `local-infer/src/local_infer/vllm_client.py:20-28` - streaming client interface.
  - Decision: `.sisyphus/evidence/task-6-route-decision.json` - selected payload shape and native model route.

  **Acceptance Criteria**:
  - [ ] `local-infer/src/local_infer/audio_store.py` or equivalent bounded audio window store exists with unit tests.
  - [ ] `local-infer/src/local_infer/audio_payloads.py` or equivalent builder creates selected native audio payload shape and is covered by unit tests.
  - [ ] `POST /v1/sessions/{id}/audio` stores audio chunks and reports stored duration/chunk count.
  - [ ] `POST /v1/sessions/{id}/generate-av-native` streams `ttft`, `token`, and `final` events and includes `audio_used_ms`, `frames_used`, `native_route`, and `total_ms`.
  - [ ] Existing `/v1/sessions/{id}/frames` and `/generate` tests remain unchanged and pass.

  **QA Scenarios**:
  ```
  Scenario: Native AV endpoint constructs explicit audio payload
    Tool: Bash
    Steps: cd /home/kio/workspace/gje/local-infer && PYTHONPATH=src pytest tests/test_app.py tests/test_frame_store.py tests/test_vllm_stream.py -q | tee ../.sisyphus/evidence/task-7-pytest.txt
    Expected: existing tests pass and new native AV tests assert payload contains an explicit audio part, not only image_url parts.
    Evidence: .sisyphus/evidence/task-7-pytest.txt

  Scenario: Missing audio fails clearly
    Tool: Bash
    Steps: cd /home/kio/workspace/gje/local-infer && PYTHONPATH=src pytest tests/test_app.py -q -k missing_audio | tee ../.sisyphus/evidence/task-7-missing-audio-test.txt
    Expected: HTTP 400 with detail containing `no audio stored for session` or equivalent exact message.
    Evidence: .sisyphus/evidence/task-7-missing-audio-test.txt
  ```

  **Commit**: NO | Message: `feat(audio): add native audio session path` | Files: [local-infer/src/local_infer/app.py, local-infer/src/local_infer/audio_store.py, local-infer/src/local_infer/audio_payloads.py, local-infer/tests/*]

- [x] 8. Add Regression and Native Audio Integration Tests

  **What to do**: Add tests for audio storage, payload construction, endpoint behavior, and selected-route integration. Include a fake native client unit test that validates exact audio/image/text payload shape without requiring GPU. Add an optional integration test marker or script that runs against the selected local native model and fixture harness. Save all test outputs to evidence. Existing six tests must continue passing.
  **Must NOT do**: Do not make GPU integration tests mandatory for normal `pytest tests -q` unless the local native server is explicitly available. Do not use manual inspection.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: test architecture plus optional GPU integration gating.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`review-work`] - Final verification wave covers review.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: [9] | Blocked By: [3, 7]

  **References**:
  - Pattern: `local-infer/tests/test_app.py:8-16` - fake vLLM client pattern.
  - Pattern: `local-infer/tests/test_app.py:31-59` - SSE body assertions and payload inspection.
  - Pattern: `local-infer/tests/test_frame_store.py:11-24` - bounded store test style.
  - Pattern: `local-infer/tests/test_vllm_stream.py:8-26` - parser tests with malformed input.
  - Evidence: `.sisyphus/evidence/task-6-route-decision.json` - selected route for integration script.

  **Acceptance Criteria**:
  - [ ] `cd local-infer && PYTHONPATH=src pytest tests -q` exits 0 and includes old + new tests.
  - [ ] Test suite covers audio chunk retention/eviction, explicit audio payload, native endpoint success with fake client, native endpoint 400 when audio missing, and no regression in frame-only endpoint.
  - [ ] Optional GPU integration command is documented in test output/evidence and does not run unless `NATIVE_AUDIO_BASE_URL` is set.
  - [ ] `.sisyphus/evidence/task-8-test-summary.txt` contains exact command output.

  **QA Scenarios**:
  ```
  Scenario: Full unit test regression
    Tool: Bash
    Steps: cd /home/kio/workspace/gje/local-infer && PYTHONPATH=src pytest tests -q | tee ../.sisyphus/evidence/task-8-test-summary.txt
    Expected: command exits 0; output shows all old and new tests passed.
    Evidence: .sisyphus/evidence/task-8-test-summary.txt

  Scenario: Optional native integration guarded by env var
    Tool: Bash
    Steps: cd /home/kio/workspace/gje/local-infer && PYTHONPATH=src pytest tests -q -k native_audio_integration
    Expected: without `NATIVE_AUDIO_BASE_URL`, test is skipped with clear reason; with it set, fixture probes must pass.
    Evidence: .sisyphus/evidence/task-8-native-integration.txt
  ```

  **Commit**: NO | Message: `test(audio): cover native audio path` | Files: [local-infer/tests/*, .sisyphus/evidence/task-8-*]

- [x] 9. Update API, Architecture, Runbook, and Decision Docs

  **What to do**: Update docs so the project language aligns with target direction and current facts. Document three layers: existing frame-only visual MVP, selected native audio route, and degraded ASR fallback (if enabled) as non-native. Update API contract with `/audio` and `/generate-av-native`. Update runbook with selected model launch command, fixture probe command, local-only verification, and GPU cleanup. Update decisions to record why 31B MP4 `video_url` audio is not accepted and which route was selected.
  **Must NOT do**: Do not call the frame-only path video+audio native. Do not hide native no-go evidence. Do not remove SGLang/vLLM historical decisions unless superseded with evidence.

  **Recommended Agent Profile**:
  - Category: `writing` - Reason: technical documentation and handoff clarity.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`frontend-ui-ux`] - No visual design.

  **Parallelization**: Can Parallel: YES after Task 6, final pass after Task 8 | Wave 4 | Blocks: [final verification] | Blocked By: [6, 8]

  **References**:
  - Pattern: `README.md:1-26` - top-level framing to keep target direction explicit.
  - Pattern: `INFERENCE_PIPELINE.md:5-10` - current scope statement that must be revised/qualified.
  - Pattern: `local-infer/README.md:9-22` - current include/exclude list where STT/TTS remains out but native audio endpoint is now in scope.
  - Pattern: `local-infer/docs/API_CONTRACT.md:19-64` - existing API format to extend.
  - Pattern: `local-infer/docs/ARCHITECTURE.md:33-50` - data-flow diagram to extend.
  - Pattern: `local-infer/docs/DECISIONS.md:33-38` - existing next-verification note to update.
  - Pattern: `local-infer/research/interaction-models-thinking-machines.md:102-148` - rationale for moving beyond frame buffer.

  **Acceptance Criteria**:
  - [ ] Docs explicitly state: current 31B frame path is visual baseline; selected route is native audio path; ASR fallback is degraded/non-native if used.
  - [ ] `local-infer/docs/API_CONTRACT.md` includes request/response examples for `/v1/sessions/{id}/audio` and `/generate-av-native`.
  - [ ] `local-infer/docs/RUNBOOK.md` includes launch/probe/cleanup commands for selected native route.
  - [ ] `local-infer/docs/DECISIONS.md` includes a new decision entry with evidence file paths from Tasks 4-6.

  **QA Scenarios**:
  ```
  Scenario: Docs contain native-vs-baseline distinction
    Tool: Bash
    Steps: grep -R "frame-only visual baseline\|native audio" README.md INFERENCE_PIPELINE.md local-infer/docs/*.md
    Expected: command finds explicit language distinguishing baseline from native audio path.
    Evidence: .sisyphus/evidence/task-9-doc-grep.txt

  Scenario: API docs include new endpoints
    Tool: Bash
    Steps: grep -E "/v1/sessions/.*/audio|generate-av-native" local-infer/docs/API_CONTRACT.md
    Expected: command exits 0 and shows both endpoint docs.
    Evidence: .sisyphus/evidence/task-9-api-docs.txt
  ```

  **Commit**: NO | Message: `docs(audio): document native audio route` | Files: [README.md, INFERENCE_PIPELINE.md, local-infer/README.md, local-infer/docs/API_CONTRACT.md, local-infer/docs/ARCHITECTURE.md, local-infer/docs/RUNBOOK.md, local-infer/docs/DECISIONS.md]

- [x] 10. Degraded Local ASR Contingency Gate

  **What to do**: Run only if Task 6 says `selected_route=native-no-go`. Produce a degraded local-only audio understanding path using local ASR/VAD sidecar plus current 31B visual path, clearly labeled **not native success**. Minimal implementation: extract/accept WAV audio, run a local ASR model or binary, pass transcript + confidence/timestamps into the existing generation prompt, and add docs that this is a contingency until native local AV model support is available. If any native route passed, create `.sisyphus/evidence/task-10-cancelled.md` and do not implement ASR.
  **Must NOT do**: Do not run if native route passed. Do not call ASR fallback native. Do not use cloud transcription.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: contingency architecture with product-labeling risk.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`mem0-cli`] - No CLI memory operations.

  **Parallelization**: Can Parallel: NO | Wave 4 | Blocks: [final verification] | Blocked By: [6]

  **References**:
  - Decision: `.sisyphus/evidence/task-6-route-decision.json` - only source that can enable this task.
  - Pattern: `local-infer/src/local_infer/app.py:66-100` - existing generation endpoint to reuse for transcript fusion if contingency enabled.
  - External: `https://huggingface.co/docs/transformers/model_doc/whisper` - local ASR fallback reference.
  - External: `https://huggingface.co/Qwen/Qwen3-ASR-1.7B` - local ASR fallback candidate.

  **Acceptance Criteria**:
  - [ ] If native route passed, `.sisyphus/evidence/task-10-cancelled.md` exists and no ASR implementation files are added.
  - [ ] If native route failed, ASR fallback has machine-verifiable transcript tests and docs label it degraded/non-native.
  - [ ] No cloud ASR or remote model API is used.

  **QA Scenarios**:
  ```
  Scenario: Contingency cancelled when native route works
    Tool: Bash
    Steps: python3 - <<'PY'
import json, pathlib
d=json.load(open('.sisyphus/evidence/task-6-route-decision.json'))
if d['selected_route'] != 'native-no-go':
    assert pathlib.Path('.sisyphus/evidence/task-10-cancelled.md').exists()
PY
    Expected: if native route selected, cancellation evidence exists.
    Evidence: .sisyphus/evidence/task-10-cancelled.md

  Scenario: Degraded fallback is not mislabeled native
    Tool: Bash
    Steps: if test -f .sisyphus/evidence/task-10-asr-fallback.md; then grep -E "degraded|non-native|fallback" .sisyphus/evidence/task-10-asr-fallback.md; fi
    Expected: fallback documentation explicitly says degraded/non-native.
    Evidence: .sisyphus/evidence/task-10-asr-fallback.md
  ```

  **Commit**: NO | Message: `feat(audio): add degraded local asr fallback` | Files: [local-infer/src/local_infer/*, local-infer/tests/*, local-infer/docs/*, .sisyphus/evidence/task-10-*]

## Final Verification Wave (MANDATORY — after ALL implementation tasks)
> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.
> **Do NOT auto-proceed after verification. Wait for user's explicit approval before marking work complete.**
> **Never mark F1-F4 as checked before getting user's okay.** Rejection or user feedback -> fix -> re-run -> present again -> wait for okay.
> All QA/review work inside F1-F4 is agent-executed with machine evidence; the user approval gate is final completion acknowledgement, not a substitute for QA.
- [x] F1. Plan Compliance Audit — oracle
- [x] F2. Code Quality Review — unspecified-high
- [x] F3. Automated Runtime QA — unspecified-high (agent-executed commands/probes; no UI unless later added)
- [x] F4. Scope Fidelity Check — deep

## Commit Strategy
- This workspace is not currently a git repo per environment metadata, so plan tasks use `Commit: NO`.
- If executor initializes or enters a git repo later, commit only after user approval and after inspecting `git status`, `git diff`, and recent log.

## Success Criteria
- A local native model route correctly answers controlled audio probes and rejects no-audio/beep hallucination cases.
- Existing 31B frame-only path still works and is documented as visual baseline, not audio-native.
- `local-infer` exposes an explicit audio-native generation path with tests and docs.
- All evidence is machine-readable and stored under `.sisyphus/evidence/`.
