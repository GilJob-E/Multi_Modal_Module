# Gemma4 Native Real Video Proof Then Streaming Refactor

## TL;DR
> **Summary**: Prove Gemma4 native multimodal analysis on the real user fixture `/home/kio/workspace/gje/vid_0033.mp4` first. Only after a verified pass, refactor `local-infer` toward a real-time rolling native-video window structure.
> **Deliverables**:
> - Auditable Gemma4 E4B/E2B local vLLM readiness and native real-video proof artifacts.
> - Real-fixture ground-truth package and pass/fail classifier for `vid_0033.mp4`.
> - Hard gate artifact that blocks all streaming refactor work unless Gemma4 passes native AV checks.
> - Native rolling MP4-window ingestion path for `local-infer` after proof passes.
> - Tests/docs/runbook updates that clearly separate native success from fallback/synthetic diagnostics.
> **Effort**: Large
> **Parallel**: YES - limited, 8 dependency-safe waves
> **Critical Path**: Task 1 → Task 2/3/4 → Task 5 → Task 6 → Task 7/8/9 → Task 10

## Context
### Original Request
User said: `내가 원하는건 아주 명확해. gemma4를 '/home/kio/workspace/gje/vid_0033.mp4' 이걸 멀티모달 네이티브 완벽 분석하는 걸 보이고, 그 다음 그걸 실시간 스트리밍 구조로 개편하는거야. 아주 쉽지? 자꾸 bullshit 같은 샛길로 새지말고. 내가 원하는 결과를 가져와. 제발`

### Interview Summary
- Success path is Gemma4 only.
- Real fixture is fixed: `/home/kio/workspace/gje/vid_0033.mp4`.
- Synthetic fixtures, Qwen substitution, ASR/VAD/rule fallback, and degraded endpoints must never count as success.
- Prior Gemma4 E4B/E2B result is reclassified as `serving_runtime_unresolved`, not model capability failure, because no native proof request was sent before readiness timeout.
- Streaming refactor begins only after a proof artifact reports `gemma4_native_real_video_pass`.

### Metis Review (gaps addressed)
- Locked model order: `google/gemma-4-E4B-it` first, `google/gemma-4-E2B-it` second only if E4B has serving/runtime no-go.
- Locked server-visible path: mount host `/home/kio/workspace/gje` to container `/workspace/gje`; use `file:///workspace/gje/vid_0033.mp4`; set `--allowed-local-media-path /workspace/gje`.
- Locked proof request: one OpenAI-compatible Gemma4 chat request with native media parts from the real fixture and text prompt; no transcript/fallback/synthetic/non-Gemma path.
- Locked pass strategy: build a real-fixture diagnostic ground-truth artifact first, then evaluate Gemma4 response against timestamped visual, audio, and cross-modal checks.
- Locked no-go taxonomy: `serving_runtime_unresolved`, `proof_invalid`, `schema_media_failure`, `gemma4_capability_no_go`, `gemma4_native_real_video_pass`.

## Work Objectives
### Core Objective
Produce auditable evidence that Gemma4 can analyze the real `vid_0033.mp4` as native multimodal input, then build the first real-time streaming structure around the same native-media principle.

### Deliverables
- `.sisyphus/evidence/vid0033-media-metadata.json`
- `.sisyphus/evidence/vid0033-ground-truth.json`
- `.sisyphus/evidence/vid0033-gemma4-readiness.json`
- `.sisyphus/evidence/vid0033-gemma4-native-proof.json`
- `.sisyphus/evidence/vid0033-native-proof-gate.json`
- `local-infer` native rolling-video-window API, tests, and docs, gated by native proof pass.

### Definition of Done (verifiable conditions with commands)
- `ffprobe -v error -show_entries format=duration,size:stream=index,codec_type,codec_name,width,height,avg_frame_rate,duration,sample_rate,channels -of json /home/kio/workspace/gje/vid_0033.mp4` confirms H.264 video, MP3 stereo audio, 640x480, 30fps, about 50.29s.
- `python3 local-infer/tools/probe_gemma4_real_video.py --base-url http://localhost:8002 --model google/gemma-4-E4B-it --video-url file:///workspace/gje/vid_0033.mp4 --ground-truth .sisyphus/evidence/vid0033-ground-truth.json --out .sisyphus/evidence/vid0033-gemma4-native-proof.json` exits 0 or writes a classified no-go artifact.
- `.sisyphus/evidence/vid0033-gemma4-native-proof.json` contains `status="gemma4_native_real_video_pass"`, `model_id`, `request_trace`, `raw_response`, `visual_check=PASS`, `audio_check=PASS`, `cross_modal_check=PASS`, `forbidden_path_checks=PASS`, and latency fields.
- If proof does not pass, `.sisyphus/evidence/vid0033-native-proof-gate.json` contains `streaming_refactor_allowed=false` and no streaming refactor tasks are executed.
- If proof passes, `cd /home/kio/workspace/gje/local-infer && PYTHONPATH=src pytest tests -q` passes after streaming refactor tasks.

### Must Have
- Gemma4-only success path: primary `google/gemma-4-E4B-it`, secondary `google/gemma-4-E2B-it` only for E4B serving/runtime no-go.
- Real fixture only: `/home/kio/workspace/gje/vid_0033.mp4` as the product proof input.
- Native media proof: model receives media parts from the real fixture, not transcript text or fallback analysis.
- Hard gate: streaming refactor starts only after `vid0033-native-proof-gate.json` says `streaming_refactor_allowed=true`.

### Must NOT Have (guardrails, AI slop patterns, scope boundaries)
- Must not use Qwen, cloud APIs, hosted ASR, or non-Gemma model as success.
- Must not use synthetic fixtures as product proof.
- Must not count `/v1/sessions/{id}/frames`, `/generate`, `/audio`, `/generate-av-fallback`, `audio_analysis.py`, ASR, VAD, or rule-based cue detection as native proof.
- Must not call Gemma4 capability no-go when the server never became ready or never accepted the native media schema.
- Must not begin streaming refactor when proof gate is not pass.

## Verification Strategy
> ZERO HUMAN INTERVENTION - all verification is agent-executed.
- Test decision: gated tests-after. Proof correctness before refactor; unit/integration tests after each code task.
- QA policy: Every task has agent-executed scenarios.
- Evidence: `.sisyphus/evidence/task-{N}-{slug}.{ext}` plus named proof artifacts above.

### Native Proof Classification Decision Tree
The proof classifier must apply these decisions in order and stop at the first match:
1. `proof_invalid`: any success artifact uses a non-Gemma model, wrong fixture, synthetic fixture, Qwen, cloud API, transcript-as-proof, `/frames`, `/generate`, `/audio`, `/generate-av-fallback`, extracted-frame-only payload, or missing request trace.
2. `serving_runtime_unresolved`: Gemma4 server never reaches a healthy request-ready state, crashes, resets connections before request, cannot load model, cannot see `/workspace/gje/vid_0033.mp4`, or times out before a native request is submitted.
3. `schema_media_failure`: server is healthy, Gemma4 model is selected, and a request is submitted, but vLLM rejects the `video_url`/`audio_url`/`input_audio` schema, rejects the MP4/MP3 container, rejects local `file://` media, or truncates media before model generation.
4. `gemma4_capability_no_go`: server is healthy, request trace is valid, native media request completes, but the model response fails visual, audio, or cross-modal checks from `.sisyphus/evidence/vid0033-ground-truth.json`.
5. `gemma4_native_real_video_pass`: server is healthy, request trace is valid, response completes, all visual/audio/cross-modal checks pass, forbidden-path checks pass, and the artifact uses only Gemma4 plus real `vid_0033.mp4` media.

## Execution Strategy
### Parallel Execution Waves
> Target: 5-8 tasks per wave. <3 per wave (except final) = under-splitting.
> Extract shared dependencies as Wave-1 tasks for max parallelism.

Wave 1: Task 1 (fixture metadata), Task 4 (harden vLLM launcher), Task 5 (guardrail classifier)
Wave 2: Task 2 (ground truth) after Task 1
Wave 3: Task 3 (proof harness) after Tasks 1-2
Wave 4: Task 6 (Gemma4 E4B/E2B proof gate) after Tasks 1-5
Wave 5: Task 7 (native window store) only if Task 6 passes
Wave 6: Task 8 (native streaming API) only if Task 6 passes and Task 7 completes
Wave 7: Task 9 (real-video streaming smoke + full tests) only if Task 6 passes and Task 8 completes
Wave 8: Task 10 (docs/runbook/evidence finalization) after Task 6 stop-state or after Tasks 7-9 if gate passes

### Dependency Matrix (full, all tasks)
- Task 1 blocks Tasks 2, 3, 6, 10.
- Task 2 blocks Tasks 3 and 6.
- Task 3 blocks Task 6.
- Task 4 blocks Task 6.
- Task 5 blocks Task 6 and Task 9.
- Task 6 blocks Tasks 7, 8, 9, 10.
- Task 7 blocks Tasks 8 and 9.
- Task 8 blocks Tasks 9 and 10.
- Task 9 blocks Task 10.
- Task 10 blocks final verification.

### Agent Dispatch Summary (wave → task count → categories)
- Wave 1 → 3 tasks → quick, unspecified-high, quick
- Wave 2 → 1 task → unspecified-high
- Wave 3 → 1 task → deep
- Wave 4 → 1 gate task → deep
- Wave 5 → 1 gated implementation task → unspecified-high
- Wave 6 → 1 gated implementation task → unspecified-high
- Wave 7 → 1 gated QA/smoke task → unspecified-high
- Wave 8 → 1 docs/evidence task → writing

## TODOs
> Implementation + Test = ONE task. Never separate.
> EVERY task MUST have: Agent Profile + Parallelization + QA Scenarios.

- [x] 1. Lock `vid_0033.mp4` Fixture Metadata and Integrity

  **What to do**: Create `.sisyphus/evidence/vid0033-media-metadata.json` and `.sisyphus/evidence/task-1-vid0033-metadata.txt` from the real file `/home/kio/workspace/gje/vid_0033.mp4`. Include absolute host path, intended container path `/workspace/gje/vid_0033.mp4`, `file://` URL, SHA256, ffprobe stream metadata, duration, size, and the statement that this is the only product proof fixture.
  **Must NOT do**: Do not use sample30.mp4, synthetic fixtures, extracted frames, or any alternate media as product proof.

  **Recommended Agent Profile**:
  - Category: `quick` - Reason: bounded metadata/evidence capture.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`mem0`] - Memory has already been updated; no SDK work.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: [2, 3, 6, 10] | Blocked By: []

  **References**:
  - Fixture: `/home/kio/workspace/gje/vid_0033.mp4` - mandatory real product proof media.
  - Research finding: ffprobe metadata showed H.264 video, MP3 stereo audio, 640x480, 30fps, about 50.29s.
  - Guardrail: `.sisyphus/drafts/crucial-multimodal-retrospective.md:3-8` - real fixture and no synthetic proof rule.

  **Acceptance Criteria**:
  - [ ] `.sisyphus/evidence/vid0033-media-metadata.json` exists with `host_path`, `container_path`, `file_url`, `sha256`, `format.duration`, and both video/audio stream entries.
  - [ ] JSON asserts `host_path == "/home/kio/workspace/gje/vid_0033.mp4"`, `container_path == "/workspace/gje/vid_0033.mp4"`, and `file_url == "file:///workspace/gje/vid_0033.mp4"`.
  - [ ] Evidence explicitly states `synthetic_product_proof_allowed=false`.

  **QA Scenarios**:
  ```
  Scenario: Real fixture metadata is captured
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && ffprobe -v error -show_entries format=duration,size:stream=index,codec_type,codec_name,width,height,avg_frame_rate,duration,sample_rate,channels -of json vid_0033.mp4
    Expected: output includes one h264 video stream, one mp3 audio stream, 640x480, 30/1 fps, and duration around 50.29s.
    Evidence: .sisyphus/evidence/task-1-vid0033-metadata.txt

  Scenario: Metadata JSON enforces real fixture only
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && python3 - <<'PY'
import json
p='.sisyphus/evidence/vid0033-media-metadata.json'
d=json.load(open(p))
assert d['host_path']=='/home/kio/workspace/gje/vid_0033.mp4'
assert d['container_path']=='/workspace/gje/vid_0033.mp4'
assert d['file_url']=='file:///workspace/gje/vid_0033.mp4'
assert d['synthetic_product_proof_allowed'] is False
assert any(s['codec_type']=='video' and s['codec_name']=='h264' for s in d['streams'])
assert any(s['codec_type']=='audio' and s['codec_name']=='mp3' for s in d['streams'])
PY
    Expected: command exits 0.
    Evidence: .sisyphus/evidence/vid0033-media-metadata.json
  ```

  **Commit**: NO | Message: `test(gemma4): lock real video fixture metadata` | Files: [.sisyphus/evidence/vid0033-*]

- [x] 2. Build Real-Fixture Ground Truth Package

  **What to do**: Create `.sisyphus/evidence/vid0033-ground-truth.json` and supporting evidence under `.sisyphus/evidence/vid0033-ground-truth/`. The artifact must contain timestamped visual events, timestamped audio/speech/sound cues, and at least one cross-modal check tying a visible moment to an audible cue. This artifact is diagnostic reference only; it cannot count as Gemma4 success. If exact speech cannot be confidently transcribed by local/non-cloud means, record an audio cue class and timestamp instead of inventing text.
  **Must NOT do**: Do not use Gemma4's proof response to write ground truth. Do not use cloud transcription. Do not fabricate content. Do not call this native proof.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: media inspection and schema creation require careful evidence handling.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`mem0-cli`] - No CLI memory work.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: [3, 6] | Blocked By: [1]

  **References**:
  - Fixture metadata: `.sisyphus/evidence/vid0033-media-metadata.json` - source identity and SHA.
  - Metis directive: ground truth must be fixture-specific and diagnostic only.
  - Oracle directive: acceptance must require audio+visual reasoning tied to the actual fixture.

  **Acceptance Criteria**:
  - [ ] `.sisyphus/evidence/vid0033-ground-truth.json` has `source_sha256`, `visual_checks`, `audio_checks`, `cross_modal_checks`, and `diagnostic_only=true`.
  - [ ] `visual_checks` contains at least three timestamped checks with expected visual observations.
  - [ ] `audio_checks` contains at least one timestamped audio/speech/sound cue from the real file.
  - [ ] `cross_modal_checks` contains at least one check requiring both visual and audio fields.
  - [ ] JSON contains `ground_truth_is_not_native_success=true`.

  **QA Scenarios**:
  ```
  Scenario: Ground truth schema is complete
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && python3 - <<'PY'
import json
d=json.load(open('.sisyphus/evidence/vid0033-ground-truth.json'))
assert d['diagnostic_only'] is True
assert d['ground_truth_is_not_native_success'] is True
assert len(d['visual_checks']) >= 3
assert len(d['audio_checks']) >= 1
assert len(d['cross_modal_checks']) >= 1
for key in ('visual_checks','audio_checks','cross_modal_checks'):
    for item in d[key]:
        assert 'timestamp_ms' in item or 'start_ms' in item
        assert 'expected' in item
PY
    Expected: command exits 0.
    Evidence: .sisyphus/evidence/vid0033-ground-truth.json

  Scenario: Ground truth uses only real fixture evidence
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && grep -E "vid_0033.mp4|diagnostic_only|not_native_success" .sisyphus/evidence/vid0033-ground-truth.json
    Expected: grep finds real fixture references and diagnostic-only labels.
    Evidence: .sisyphus/evidence/vid0033-ground-truth.json
  ```

  **Commit**: NO | Message: `test(gemma4): create real video ground truth` | Files: [.sisyphus/evidence/vid0033-ground-truth*]

- [x] 3. Add Native Gemma4 Real-Video Proof Harness

  **What to do**: Add `local-infer/tools/probe_gemma4_real_video.py`. It must send one OpenAI-compatible `/v1/chat/completions` request to a local vLLM server using Gemma4 and the real fixture. Required args: `--base-url`, `--model`, `--video-url`, `--ground-truth`, `--out`, `--timeout`, `--mode`. It must record raw request trace, raw response, timing, model id, media parts, and guardrail checks. Preferred mode is `direct_video`; if vLLM requires separate audio, support `video_plus_audio_from_same_fixture` with SHA/ffmpeg provenance and still forbid transcript text.
  **Must NOT do**: Do not call local-infer fallback endpoints. Do not use Qwen. Do not use synthetic fixtures. Do not inject ground-truth answers into the prompt. Do not use extracted-frame-only proof.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: proof harness defines the core success semantics.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`mem0`] - No memory SDK work.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: [6] | Blocked By: [1, 2]

  **References**:
  - Pattern: `local-infer/tools/probe_native_audio.py` - JSON evidence, pass/fail normalization, explicit media payload style.
  - Pattern: `video-test/infer.py` - simple OpenAI-compatible video request pattern.
  - Pattern: `video-test/infer_ttft.py` - TTFT/timing pattern for MP4 request.
  - Docs: vLLM multimodal inputs support `video_url`, `audio_url`, and `input_audio` content parts.

  **Acceptance Criteria**:
  - [ ] `local-infer/tools/probe_gemma4_real_video.py` exists and supports all required args.
  - [ ] Dry-run mode writes request metadata containing `file:///workspace/gje/vid_0033.mp4` and no forbidden paths.
  - [ ] Output JSON schema includes `status`, `no_go_type`, `model_id`, `request_trace`, `raw_response`, `visual_check`, `audio_check`, `cross_modal_check`, `forbidden_path_checks`, `ttft_ms`, and `total_ms`.
  - [ ] Harness exits nonzero only for harness/runtime errors; model failures must still write classified JSON.

  **QA Scenarios**:
  ```
  Scenario: Dry-run proves exact native media request shape
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && python3 local-infer/tools/probe_gemma4_real_video.py --dry-run --base-url http://localhost:8002 --model google/gemma-4-E4B-it --video-url file:///workspace/gje/vid_0033.mp4 --ground-truth .sisyphus/evidence/vid0033-ground-truth.json --out .sisyphus/evidence/task-3-real-video-dry-run.json
    Expected: command exits 0 and JSON request_trace contains video_url file:///workspace/gje/vid_0033.mp4, model google/gemma-4-E4B-it, and forbidden_path_checks=PASS.
    Evidence: .sisyphus/evidence/task-3-real-video-dry-run.json

  Scenario: Harness rejects wrong fixture
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && python3 local-infer/tools/probe_gemma4_real_video.py --dry-run --base-url http://localhost:8002 --model google/gemma-4-E4B-it --video-url file:///workspace/gje/video-test/sample30.mp4 --ground-truth .sisyphus/evidence/vid0033-ground-truth.json --out .sisyphus/evidence/task-3-wrong-fixture.json; test $? -ne 0
    Expected: command exits nonzero or writes proof_invalid; wrong fixture cannot be accepted.
    Evidence: .sisyphus/evidence/task-3-wrong-fixture.json
  ```

  **Commit**: NO | Message: `test(gemma4): add real video native probe` | Files: [local-infer/tools/probe_gemma4_real_video.py, .sisyphus/evidence/task-3-*]

- [x] 4. Harden Gemma4 vLLM Readiness and Local Media Launch

  **What to do**: Add or update a launch/probe wrapper so Gemma4 E4B then E2B are started with robust local-media settings. Required Docker behavior: mount `/home/kio/hf_cache` to `/root/.cache/huggingface`, mount `/home/kio/workspace/gje` read-only to `/workspace/gje`, expose host port `127.0.0.1:8002`, set `VLLM_ENGINE_READY_TIMEOUT_S=3600`, use `--allowed-local-media-path /workspace/gje`, set `--limit-mm-per-prompt {"video":1,"audio":1,"image":4}`, and collect logs/GPU/memory/cache evidence. Prefer `--ipc=host`; if not allowed, use explicit large `--shm-size` and record it.
  **Must NOT do**: Do not stop the working baseline container unless needed and documented. Do not classify model capability on readiness failure. Do not omit local media mount.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: GPU/runtime launch and readiness evidence are operationally sensitive.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`frontend-ui-ux`] - No UI work.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: [6] | Blocked By: []

  **References**:
  - Pattern: `local-infer/tools/probe_gemma4_vllm_sequence.py:347-409` - existing model sequence and readiness workflow.
  - Evidence: `.sisyphus/evidence/task-4-gemma4-no-go.md:6-42` - prior readiness timeout before probe.
  - Pattern: `sglang/launch-configs/vllm_baseline.sh` - current vLLM baseline launch conventions.
  - Docs: vLLM `VLLM_ENGINE_READY_TIMEOUT_S`, `--allowed-local-media-path`, multimodal limits, and Docker shared memory guidance.

  **Acceptance Criteria**:
  - [ ] Launch wrapper writes `.sisyphus/evidence/vid0033-gemma4-readiness.json` with model id, command, image, mounts, env, readiness timeout, vLLM version if available, GPU snapshot, and final readiness status.
  - [ ] If readiness fails, status is `serving_runtime_unresolved`, not capability no-go.
  - [ ] Evidence contains `/workspace/gje` mount and `--allowed-local-media-path /workspace/gje`.

  **QA Scenarios**:
  ```
  Scenario: Launch command includes real media mount and long readiness timeout
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && python3 - <<'PY'
import json
d=json.load(open('.sisyphus/evidence/vid0033-gemma4-readiness.json'))
cmd=' '.join(d.get('command', [])) if isinstance(d.get('command'), list) else d.get('command','')
assert '/workspace/gje' in cmd
assert '--allowed-local-media-path' in cmd
assert 'VLLM_ENGINE_READY_TIMEOUT_S' in d.get('env', {}) or 'VLLM_ENGINE_READY_TIMEOUT_S=3600' in cmd
assert d['classification'] in {'ready','serving_runtime_unresolved'}
PY
    Expected: command exits 0.
    Evidence: .sisyphus/evidence/vid0033-gemma4-readiness.json

  Scenario: Readiness failure is not capability failure
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && python3 - <<'PY'
import json
d=json.load(open('.sisyphus/evidence/vid0033-gemma4-readiness.json'))
if d['classification'] != 'ready':
    assert d['classification'] == 'serving_runtime_unresolved'
    assert 'capability' not in d.get('failure_reason','').lower()
PY
    Expected: command exits 0.
    Evidence: .sisyphus/evidence/vid0033-gemma4-readiness.json
  ```

  **Commit**: NO | Message: `ops(gemma4): harden real video readiness` | Files: [local-infer/tools/*gemma4*, .sisyphus/evidence/vid0033-gemma4-readiness.json]

- [x] 5. Implement Proof Guardrail and No-Go Classifier

  **What to do**: Add proof classification logic, either inside `probe_gemma4_real_video.py` or as `local-infer/tools/verify_vid0033_native_proof.py`. It must classify every result as exactly one of `serving_runtime_unresolved`, `proof_invalid`, `schema_media_failure`, `gemma4_capability_no_go`, or `gemma4_native_real_video_pass`. It must inspect request trace for forbidden paths and assert the proof uses Gemma4 plus real fixture media.
  **Must NOT do**: Do not make fuzzy/implicit pass decisions. Do not allow fallback endpoints or synthetic fixture strings anywhere in a pass artifact.

  **Recommended Agent Profile**:
  - Category: `quick` - Reason: bounded JSON classifier and assertions.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`mem0-cli`] - No CLI memory work.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: [6, 9] | Blocked By: []

  **References**:
  - Evidence: `.sisyphus/evidence/task-6-route-decision.json:5-16` - prior fallback distinction to preserve.
  - Guardrail: `.sisyphus/drafts/crucial-multimodal-retrospective.md:3-22` - native/fallback and readiness classification correction.
  - Pattern: `local-infer/tests/test_app.py:121-127` - current fallback explicitly reports `native_success is False`; pass classifier must reject that path.

  **Acceptance Criteria**:
  - [ ] Classifier rejects artifacts containing `Qwen`, `generate-av-fallback`, `/audio`, `/frames`, `audio_analysis`, `cross_modal_event`, `sample30.mp4`, or `native_success=false` as proof pass.
  - [ ] Classifier accepts pass only when model id starts with `google/gemma-4-`, fixture file URL is `file:///workspace/gje/vid_0033.mp4`, and all three checks pass.
  - [ ] Classifier writes `.sisyphus/evidence/vid0033-native-proof-gate.json` with `streaming_refactor_allowed` boolean.

  **QA Scenarios**:
  ```
  Scenario: Forbidden fallback artifact cannot pass
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && python3 local-infer/tools/verify_vid0033_native_proof.py --proof .sisyphus/evidence/task-10-audio-analysis.json --out .sisyphus/evidence/task-5-forbidden-proof-check.json; test $? -ne 0
    Expected: command exits nonzero or writes proof_invalid; degraded local audio analysis cannot pass.
    Evidence: .sisyphus/evidence/task-5-forbidden-proof-check.json

  Scenario: Gate JSON schema is deterministic
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && python3 - <<'PY'
import json, pathlib
p=pathlib.Path('.sisyphus/evidence/vid0033-native-proof-gate.json')
if p.exists():
    d=json.load(open(p))
    assert 'status' in d
    assert 'streaming_refactor_allowed' in d
    assert d['status'] in {'serving_runtime_unresolved','proof_invalid','schema_media_failure','gemma4_capability_no_go','gemma4_native_real_video_pass'}
PY
    Expected: command exits 0 whether gate exists yet or not.
    Evidence: .sisyphus/evidence/vid0033-native-proof-gate.json
  ```

  **Commit**: NO | Message: `test(gemma4): classify native proof gate` | Files: [local-infer/tools/verify_vid0033_native_proof.py, .sisyphus/evidence/task-5-*]

- [x] 6. Execute Gemma4 Real-Video Native Proof Gate

  **What to do**: Run the hardened Gemma4 sequence. Attempt E4B first. If E4B produces `serving_runtime_unresolved`, attempt E2B. For the first model that becomes ready, run `probe_gemma4_real_video.py` against `file:///workspace/gje/vid_0033.mp4` and the real ground truth. Write `.sisyphus/evidence/vid0033-gemma4-native-proof.json` and `.sisyphus/evidence/vid0033-native-proof-gate.json`. If no pass, stop downstream refactor work and document the exact classified stop state.
  **Must NOT do**: Do not proceed to Tasks 7-9 unless gate says `streaming_refactor_allowed=true`. Do not change model family. Do not “rescue” failure with fallback or synthetic proof.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: core runtime proof gate with branching no-go semantics.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`mem0`] - No memory SDK work.

  **Parallelization**: Can Parallel: NO | Wave 4 | Blocks: [7, 8, 9, 10] | Blocked By: [1, 2, 3, 4, 5]

  **References**:
  - Harness: `local-infer/tools/probe_gemma4_real_video.py` - real video proof request.
  - Launcher: `local-infer/tools/probe_gemma4_vllm_sequence.py` or successor - model startup/readiness sequence.
  - Ground truth: `.sisyphus/evidence/vid0033-ground-truth.json` - fixture-specific expected checks.
  - Oracle directive: streaming refactor is blocked until native proof passes.

  **Acceptance Criteria**:
  - [ ] `.sisyphus/evidence/vid0033-gemma4-native-proof.json` exists for any ready model request or `.sisyphus/evidence/vid0033-gemma4-readiness.json` records serving stop state.
  - [ ] `.sisyphus/evidence/vid0033-native-proof-gate.json` exists and has one of the five locked statuses.
  - [ ] If status is `gemma4_native_real_video_pass`, all visual/audio/cross-modal checks are PASS and `streaming_refactor_allowed=true`.
  - [ ] If status is not pass, `streaming_refactor_allowed=false` and Tasks 7-9 must be cancelled with evidence rather than executed.

  **QA Scenarios**:
  ```
  Scenario: Native proof gate is explicit
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && python3 - <<'PY'
import json
d=json.load(open('.sisyphus/evidence/vid0033-native-proof-gate.json'))
allowed={'serving_runtime_unresolved','proof_invalid','schema_media_failure','gemma4_capability_no_go','gemma4_native_real_video_pass'}
assert d['status'] in allowed
assert isinstance(d['streaming_refactor_allowed'], bool)
if d['status'] == 'gemma4_native_real_video_pass':
    assert d['streaming_refactor_allowed'] is True
else:
    assert d['streaming_refactor_allowed'] is False
PY
    Expected: command exits 0.
    Evidence: .sisyphus/evidence/vid0033-native-proof-gate.json

  Scenario: Pass artifact contains no forbidden sidetrack
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && if python3 - <<'PY'
import json
gate=json.load(open('.sisyphus/evidence/vid0033-native-proof-gate.json'))
raise SystemExit(0 if gate['status']=='gemma4_native_real_video_pass' else 1)
PY
then ! grep -R -E "Qwen|generate-av-fallback|cross_modal_event|sample30|audio_analysis|native_success.*false" .sisyphus/evidence/vid0033-gemma4-native-proof.json; fi
    Expected: if pass, grep finds no forbidden sidetrack strings.
    Evidence: .sisyphus/evidence/vid0033-gemma4-native-proof.json
  ```

  **Commit**: NO | Message: `test(gemma4): execute real video native proof` | Files: [.sisyphus/evidence/vid0033-*]

- [x] 7. Add Native Rolling Video Window Store (Gated, Cancelled - proof gate failed)

  **What to do**: Only if Task 6 passes, add `local-infer/src/local_infer/native_media_store.py`. Store per-session rolling MP4 windows from real-time clients as bounded runtime files, not extracted JPEG frames. Each window has `session_id`, `start_ms`, `end_ms`, `video_mp4_base64`, `sha256`, `mime_type`, and server-local file URL. Enforce max windows and max bytes. Use a runtime temp directory configurable by environment variable and defaulting outside repo-tracked paths.
  **Must NOT do**: Do not reuse `FrameStore` as proof of native video. Do not store transcripts. Do not call `audio_analysis.py`.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: new state component with safety limits.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`frontend-ui-ux`] - No UI work.

  **Parallelization**: Can Parallel: NO | Wave 5 | Blocks: [8, 9] | Blocked By: [6 pass]

  **References**:
  - Pattern: `local-infer/src/local_infer/frame_store.py:15-55` - bounded per-session store pattern.
  - Pattern: `local-infer/src/local_infer/audio_store.py:25-85` - bounded per-session chunk store pattern, but not native success path.
  - Gate: `.sisyphus/evidence/vid0033-native-proof-gate.json` - must allow refactor.

  **Acceptance Criteria**:
  - [ ] `native_media_store.py` exists with bounded window retention and validation.
  - [ ] Tests prove max-window eviction, wrong session isolation, invalid base64 rejection, size-limit rejection, and local file URL generation.
  - [ ] Tests assert no dependency on `audio_analysis.py` or fallback endpoints.

  **QA Scenarios**:
  ```
  Scenario: Store preserves only bounded native MP4 windows
    Tool: Bash
    Steps: cd /home/kio/workspace/gje/local-infer && PYTHONPATH=src pytest tests/test_native_media_store.py -q
    Expected: tests pass and cover eviction/session isolation.
    Evidence: .sisyphus/evidence/task-7-native-media-store-pytest.txt

  Scenario: Gate prevents accidental execution when proof failed
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && python3 - <<'PY'
import json
d=json.load(open('.sisyphus/evidence/vid0033-native-proof-gate.json'))
assert d['streaming_refactor_allowed'] is True, 'Task 7 must be cancelled unless proof gate passed'
PY
    Expected: command exits 0 before Task 7 changes are applied; otherwise executor cancels Task 7 with evidence.
    Evidence: .sisyphus/evidence/task-7-gate-check.txt
  ```

  **Commit**: NO | Message: `feat(native): add rolling video window store` | Files: [local-infer/src/local_infer/native_media_store.py, local-infer/tests/test_native_media_store.py]

- [x] 8. Add Native Streaming Window API and Payload Builder (Gated, Cancelled - proof gate failed)

  **What to do**: Only if Task 6 passes, add native endpoints and payload helpers. Add `local-infer/src/local_infer/native_payloads.py`. Extend `app.py` with `POST /v1/native/sessions/{session_id}/windows` to ingest rolling MP4 windows and `POST /v1/native/sessions/{session_id}/generate` to send the latest valid window to Gemma4 as native `video_url` media. Stream Gemma4 tokens as SSE like current `/generate`, but use native media file URL from `NativeMediaStore`. Include `native_success_candidate=true` only for the request path, not for final proof unless model response passes checks.
  **Must NOT do**: Do not modify existing `/frames` + `/generate` behavior except shared helper extraction if tests prove no regression. Do not call fallback audio endpoints. Do not send JPEG `image_url[]` in the native streaming path.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: API and payload extension with strict guardrails.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`mem0-vercel-ai-sdk`] - No Vercel AI SDK work.

  **Parallelization**: Can Parallel: NO | Wave 6 | Blocks: [9, 10] | Blocked By: [6 pass, 7]

  **References**:
  - Pattern: `local-infer/src/local_infer/app.py:84-148` - current frame ingest and SSE generation style.
  - Pattern: `local-infer/src/local_infer/payloads.py:11-57` - current payload builder to avoid in native video path.
  - Pattern: `local-infer/src/local_infer/vllm_client.py` - vLLM streaming client adapter.
  - Contract: `local-infer/docs/API_CONTRACT.md:19-64` - current API contract to extend without breaking.

  **Acceptance Criteria**:
  - [ ] `POST /v1/native/sessions/{session_id}/windows` stores a base64 MP4 window and returns count, duration, and SHA.
  - [ ] `POST /v1/native/sessions/{session_id}/generate` builds a vLLM payload containing `video_url` for the stored MP4 window and no `image_url` frames.
  - [ ] Existing `/v1/sessions/{id}/frames` and `/v1/sessions/{id}/generate` tests still pass.
  - [ ] Native endpoint tests assert forbidden fallback paths are not called.

  **QA Scenarios**:
  ```
  Scenario: Native generate uses video_url not image_url fallback
    Tool: Bash
    Steps: cd /home/kio/workspace/gje/local-infer && PYTHONPATH=src pytest tests/test_native_app.py -q
    Expected: tests pass and inspect fake vLLM payload containing video_url and no image_url[] parts.
    Evidence: .sisyphus/evidence/task-8-native-app-pytest.txt

  Scenario: Existing frame path is not regressed
    Tool: Bash
    Steps: cd /home/kio/workspace/gje/local-infer && PYTHONPATH=src pytest tests/test_app.py tests/test_frame_store.py -q
    Expected: existing frame/fallback tests pass; native additions do not break old behavior.
    Evidence: .sisyphus/evidence/task-8-regression-pytest.txt
  ```

  **Commit**: NO | Message: `feat(native): add rolling video window API` | Files: [local-infer/src/local_infer/app.py, local-infer/src/local_infer/native_payloads.py, local-infer/tests/test_native_app.py]

- [x] 9. Add Real-Video Streaming Smoke Runner and Full Test Gate (Gated, Cancelled - proof gate failed)

  **What to do**: Only if Task 6 passes, add `local-infer/tools/smoke_vid0033_native_stream.py`. It must derive rolling short MP4 windows from `/home/kio/workspace/gje/vid_0033.mp4`, push them through the new native window API, call native generate, and save SSE timing/response evidence. This is a streaming-structure smoke, not the original proof gate. Also run full local-infer tests and guardrail checks.
  **Must NOT do**: Do not call frame endpoint for this smoke. Do not use generated synthetic media. Do not call ASR/fallback endpoints.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: end-to-end runtime smoke plus regression gate.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`mem0-cli`] - No memory CLI work.

  **Parallelization**: Can Parallel: NO | Wave 7 | Blocks: [10] | Blocked By: [6 pass, 7, 8]

  **References**:
  - Pattern: `video-test/infer_ttft.py` - timing and streaming measurement style.
  - Pattern: `video-test/bench_nframe.py` - benchmark evidence output style, but do not reuse image_url as native proof.
  - Gate: `.sisyphus/evidence/vid0033-native-proof-gate.json` - streaming smoke allowed only after pass.

  **Acceptance Criteria**:
  - [ ] Smoke runner writes `.sisyphus/evidence/task-9-native-stream-smoke.json` with windows pushed, native endpoint response, TTFT, total latency, and forbidden path checks.
  - [ ] Full `local-infer` pytest passes and output is saved to `.sisyphus/evidence/task-9-pytest.txt`.
  - [ ] Smoke evidence uses `/home/kio/workspace/gje/vid_0033.mp4` as source and native video window endpoint as transport.

  **QA Scenarios**:
  ```
  Scenario: Native streaming smoke uses real video windows
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && python3 local-infer/tools/smoke_vid0033_native_stream.py --base-url http://localhost:8080 --source /home/kio/workspace/gje/vid_0033.mp4 --out .sisyphus/evidence/task-9-native-stream-smoke.json
    Expected: command exits 0 or writes classified runtime failure; JSON references vid_0033.mp4 and native windows endpoint only.
    Evidence: .sisyphus/evidence/task-9-native-stream-smoke.json

  Scenario: Full local-infer tests pass after gated refactor
    Tool: Bash
    Steps: cd /home/kio/workspace/gje/local-infer && PYTHONPATH=src pytest tests -q | tee ../.sisyphus/evidence/task-9-pytest.txt
    Expected: command exits 0.
    Evidence: .sisyphus/evidence/task-9-pytest.txt
  ```

  **Commit**: NO | Message: `test(native): add real video streaming smoke` | Files: [local-infer/tools/smoke_vid0033_native_stream.py, local-infer/tests/*, .sisyphus/evidence/task-9-*]

- [x] 10. Update Docs, Runbook, and Stop-State Evidence

  **What to do**: Update docs to reflect the new gate and final state. If Task 6 did not pass, document stop-state and do not describe streaming implementation as available. If Task 6 passed and Tasks 7-9 ran, update API docs/runbook/architecture for native rolling MP4 window endpoints. Always document that degraded fallback is not native success.
  **Must NOT do**: Do not claim Gemma4 works unless `vid0033-native-proof-gate.json` says pass. Do not bury the proof gate.

  **Recommended Agent Profile**:
  - Category: `writing` - Reason: docs/runbook/evidence consolidation.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`mem0`] - No memory SDK work.

  **Parallelization**: Can Parallel: NO | Wave 8 | Blocks: [final verification] | Blocked By: [6, 8, 9 if gate passed]

  **References**:
  - Current docs: `local-infer/docs/API_CONTRACT.md:1-72`, `local-infer/docs/ARCHITECTURE.md:1-66`, `local-infer/docs/RUNBOOK.md:31-65`.
  - Current README: `local-infer/README.md:1-109`.
  - Retrospective: `.sisyphus/drafts/crucial-multimodal-retrospective.md:3-25`.

  **Acceptance Criteria**:
  - [ ] `.sisyphus/evidence/task-10-final-state.md` states exact gate status and whether streaming refactor was executed or cancelled.
  - [ ] Docs mention `/home/kio/workspace/gje/vid_0033.mp4` as the real proof fixture and distinguish proof pass vs stop state.
  - [ ] Docs explicitly say fallback/synthetic/Qwen/ASR/VAD paths are not native Gemma4 success.
  - [ ] If native endpoints exist, `API_CONTRACT.md` documents request/response examples and guardrails.

  **QA Scenarios**:
  ```
  Scenario: Final docs expose native gate status
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && grep -R -E "vid_0033.mp4|native proof gate|streaming_refactor_allowed|fallback.*not.*native" local-infer/docs local-infer/README.md .sisyphus/evidence/task-10-final-state.md
    Expected: grep finds real fixture, gate, and fallback-not-native statements.
    Evidence: .sisyphus/evidence/task-10-final-state.md

  Scenario: Stop-state or API docs are consistent with gate
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && python3 - <<'PY'
import json, pathlib
gate=json.load(open('.sisyphus/evidence/vid0033-native-proof-gate.json'))
text=pathlib.Path('.sisyphus/evidence/task-10-final-state.md').read_text()
if gate['streaming_refactor_allowed']:
    assert 'streaming refactor executed' in text or 'native rolling' in text
else:
    assert 'streaming refactor cancelled' in text or 'not executed' in text
PY
    Expected: command exits 0.
    Evidence: .sisyphus/evidence/task-10-final-state.md
  ```

  **Commit**: NO | Message: `docs(native): document Gemma4 proof gate and streaming state` | Files: [local-infer/docs/*, local-infer/README.md, .sisyphus/evidence/task-10-final-state.md]

## Final Verification Wave (MANDATORY — after ALL implementation tasks)
> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.
> **Do NOT auto-proceed after verification. Wait for user's explicit approval before marking work complete.**
> **Never mark F1-F4 as checked before getting user's okay.** Rejection or user feedback -> fix -> re-run -> present again -> wait for okay.
- [x] F1. Plan Compliance Audit — oracle
- [x] F2. Code Quality Review — unspecified-high
- [x] F3. Native Runtime QA — unspecified-high (Gemma4 proof artifacts + pytest; no UI unless later added)
- [x] F4. Scope Fidelity Check — deep

## Commit Strategy
- Environment metadata says this workspace is not a git repo, so plan tasks use `Commit: NO`.
- If executor later enters a git repo, commit only after user approval and after inspecting `git status`, `git diff`, and recent log.

## Success Criteria
- Gemma4 native proof on `/home/kio/workspace/gje/vid_0033.mp4` either passes with auditable evidence or stops with a correctly classified serving/schema/capability no-go.
- No fallback, synthetic, Qwen, ASR, VAD, or frame-only path is ever counted as success.
- Streaming refactor exists only if native proof gate passes.
- Documentation makes the gate and native/fallback separation impossible to miss.
