# Native Streaming Refactor — User Override Capability Go

## TL;DR
> **Summary**: Add a separate native rolling MP4-window streaming path to `local-infer`, authorized by the user's explicit capability override. The prior proof artifacts remain canonical (`gemma4_capability_no_go`, `streaming_refactor_allowed=false`); this plan records a new `user_override_capability_go_for_refactor` decision and proceeds without falsifying history.
> **Deliverables**:
> - User-override evidence artifact.
> - Native rolling MP4 window store with bounded temp-file retention.
> - Same-window native audio transport as `input_audio` from uploaded MP4 windows; no ASR/VAD/rule analysis.
> - Native payload builder using `video_url` + same-window `input_audio`, never `image_url[]`.
> - Native upload and native generate SSE endpoints.
> - Real `vid_0033.mp4` streaming-structure smoke runner.
> - Tests, guardrails, docs, and final verification.
> **Effort**: Medium
> **Parallel**: YES - 5 waves
> **Critical Path**: Task 1 → Tasks 2/3 → Task 4 → Task 5 → Tasks 6/7 → Task 8

## Context
### Original Request
User originally wanted Gemma4 native multimodal proof on `/home/kio/workspace/gje/vid_0033.mp4`, then real-time streaming refactor. After final no-go reporting, user said: `아냐. 그정도면 capab go야. refactor 진행해`.

### Interview Summary
- User explicitly overrides the previous gate interpretation and treats the accepted E4B native media result as sufficient capability signal.
- Prior canonical artifacts must remain unchanged: `.sisyphus/evidence/vid0033-native-proof-gate.json` still says `gemma4_capability_no_go`, `streaming_refactor_allowed=false`.
- This plan authorizes refactor via a separate decision label: `user_override_capability_go_for_refactor`.
- Existing `local-infer` frame and degraded fallback endpoints must remain intact and must not be presented as native success.

### Metis Review (gaps addressed)
- Native API shape is fixed in this plan: `POST /v1/native/sessions/{session_id}/windows` and `POST /v1/native/sessions/{session_id}/generate`.
- Upload format is fixed: JSON base64 MP4 windows, matching current API/test style and avoiding multipart churn.
- Rolling semantics are fixed: keep most recent N MP4 windows per session plus a total bytes limit; evict oldest windows.
- Payload shape is fixed: latest native MP4 window as `video_url`; same-window extracted audio as OpenAI-compatible `input_audio` WAV when extraction succeeds; no image frames.
- Override evidence location is fixed: `.sisyphus/evidence/native-streaming-user-override-go.json`.
- Smoke success is structural: native endpoints reached, payload contains `video_url` and `input_audio`, no `image_url`, no fallback used, SSE response non-empty.

## Work Objectives
### Core Objective
Implement an additive native streaming structure that accepts rolling MP4 windows and sends the latest window to Gemma4/vLLM as native media, without reusing frame-only or fallback routes as success.

### Deliverables
- `.sisyphus/evidence/native-streaming-user-override-go.json`
- `local-infer/src/local_infer/native_media_store.py`
- `local-infer/src/local_infer/native_audio.py`
- `local-infer/src/local_infer/native_payloads.py`
- Native endpoints in `local-infer/src/local_infer/app.py`
- `local-infer/tools/smoke_vid0033_native_stream.py`
- Tests: `test_native_media_store.py`, `test_native_audio.py`, `test_native_payloads.py`, `test_native_app.py`, `test_native_forbidden_paths.py`
- Updated `local-infer` docs/runbook/README plus top-level gate note if needed

### Definition of Done (verifiable conditions with commands)
- `cd /home/kio/workspace/gje/local-infer && PYTHONPATH=src uv run --with pytest --with httpx pytest tests/test_native_media_store.py tests/test_native_audio.py tests/test_native_payloads.py tests/test_native_app.py tests/test_native_forbidden_paths.py -q` exits 0.
- `cd /home/kio/workspace/gje/local-infer && PYTHONPATH=src uv run --with pytest --with httpx pytest tests -q` exits 0.
- `cd /home/kio/workspace/gje && python3 local-infer/tools/smoke_vid0033_native_stream.py --source /home/kio/workspace/gje/vid_0033.mp4 --out .sisyphus/evidence/native-streaming-vid0033-smoke.json --in-process-fake-vllm` exits 0 and writes native payload evidence.
- Smoke evidence asserts `video_url_present=true`, `input_audio_present=true`, `image_url_present=false`, `fallback_used=false`, and `response_non_empty=true`.
- Docs state the refactor was authorized by `user_override_capability_go_for_refactor`, not by rewriting the prior proof gate.

### Must Have
- Separate native route namespace under `/v1/native/sessions/{session_id}/...`.
- Bounded temp-file store using `LOCAL_INFER_NATIVE_MEDIA_DIR`, default `/tmp/gje-local-infer-native-media`.
- Container-visible media URL mapping using `LOCAL_INFER_NATIVE_MEDIA_URL_PREFIX`; default is `file://{host_dir}` for non-container local runs, runbook must document Docker/vLLM mount setup.
- Same-window audio transport only: extract WAV/input_audio from uploaded MP4 window for native model input; no transcript, ASR, VAD, rule detection, or `audio_analysis.py`.
- Native payload builder uses OpenAI/vLLM content shape: `{"type":"video_url","video_url":{"url":"file://...mp4"}}` plus `{"type":"input_audio","input_audio":{"data":"<base64>","format":"wav"}}` plus text.
- Existing `/frames`, `/generate`, `/audio`, and `/generate-av-fallback` behavior remains unchanged.

### Native API Request/Response Schemas (locked)
`NativeWindowIn` request body for `POST /v1/native/sessions/{session_id}/windows`:
```json
{
  "start_ms": 12000,
  "end_ms": 17000,
  "video_mp4_base64": "<base64 mp4 bytes>",
  "mime_type": "video/mp4"
}
```
- `start_ms`: integer `>=0`.
- `end_ms`: integer, must be `> start_ms` and duration must be `<=30000`.
- `video_mp4_base64`: non-empty base64 string; decoded bytes must be non-empty and under configured max bytes.
- `mime_type`: exactly `video/mp4`; any other MIME returns 400.

`NativeWindowStored` response:
```json
{
  "session_id": "demo",
  "stored_windows": 1,
  "latest_sha256": "...",
  "latest_duration_ms": 5000,
  "latest_video_url": "file:///native-media/demo/<sha>.mp4"
}
```

`NativeGenerateIn` request body for `POST /v1/native/sessions/{session_id}/generate`:
```json
{
  "prompt": "지원자의 현재 답변과 태도를 짧게 보고 후속 질문 하나를 해줘.",
  "system_prompt": "당신은 한국어 화상 면접관입니다...",
  "max_tokens": 128,
  "temperature": 0.2,
  "model": null,
  "stream": true
}
```
- `prompt`: non-empty string.
- `system_prompt`: defaults to `DEFAULT_NATIVE_SYSTEM_PROMPT`.
- `max_tokens`: integer `1..1024`.
- `temperature`: float `0.0..2.0`.
- `model`: optional string; `null` means existing `MODEL` env value.
- `stream`: must be `true`; `false` returns 400 because endpoint is SSE-only.

Native generate final SSE event must include:
```json
{
  "type": "final",
  "text": "...",
  "native_media_mode": "video_url_plus_input_audio",
  "video_sha256": "...",
  "video_url": "file:///...mp4",
  "input_audio_present": true,
  "fallback_used": false,
  "total_ms": 123.4
}
```

### Must NOT Have (guardrails, AI slop patterns, scope boundaries)
- Must not edit `.sisyphus/evidence/vid0033-native-proof-gate.json` to pass.
- Must not claim the previous proof artifact became `gemma4_native_real_video_pass`.
- Must not use Qwen, cloud APIs, hosted ASR, VAD/rule fallback, transcript-as-proof, synthetic fixtures, or frame-only proof as native success.
- Must not route native streaming through `/audio` or `/generate-av-fallback`.
- Must not import or call `audio_analysis.py` from the native path.
- Must not send `image_url[]` from `/v1/native/.../generate`.
- Must not rewrite the whole app or replace the existing frame path.

## Verification Strategy
> ZERO HUMAN INTERVENTION - all verification is agent-executed.
- Test decision: tests-after, with unit tests for each new module and full regression suite after API integration.
- QA policy: Every task has agent-executed happy/failure scenarios.
- Evidence: `.sisyphus/evidence/task-{N}-{slug}.{ext}` plus `.sisyphus/evidence/native-streaming-vid0033-smoke.json`.

## Execution Strategy
### Parallel Execution Waves
> Target: 5-8 tasks per wave. This refactor has strict dependencies, so Wave 1 carries all independent foundation tasks; later waves are dependency-bound.

Wave 1: Tasks 1, 2, 3 — override evidence, native store, native audio transport.
Wave 2: Task 4 — native payload builder after store/audio interfaces are fixed.
Wave 3: Task 5 — native FastAPI endpoints and SSE integration.
Wave 4: Tasks 6, 7 — real fixture smoke runner and docs/runbook update.
Wave 5: Task 8 — full verification and review handoff.

### Dependency Matrix (full, all tasks)
- Task 1 blocks Tasks 7 and 8.
- Task 2 blocks Tasks 4, 5, 6, 8.
- Task 3 blocks Tasks 4, 5, 6, 8.
- Task 4 blocks Tasks 5, 6, 8.
- Task 5 blocks Tasks 6, 7, 8.
- Task 6 blocks Task 8.
- Task 7 blocks Task 8.
- Task 8 blocks final verification.

### Agent Dispatch Summary (wave → task count → categories)
- Wave 1 → 3 tasks → quick, unspecified-high, unspecified-high
- Wave 2 → 1 task → unspecified-high
- Wave 3 → 1 task → unspecified-high
- Wave 4 → 2 tasks → unspecified-high, writing
- Wave 5 → 1 task → unspecified-high

## TODOs
> Implementation + Test = ONE task. Never separate.
> EVERY task MUST have: Agent Profile + Parallelization + QA Scenarios.

- [x] 1. Record User Override Capability-Go Decision

  **What to do**: Create `.sisyphus/evidence/native-streaming-user-override-go.json`. It must record the exact user quote, timestamp, prior canonical gate path/status, final proof summary, and new authorization label `user_override_capability_go_for_refactor`. It must explicitly state that `.sisyphus/evidence/vid0033-native-proof-gate.json` remains canonical historical no-go and is not being edited to pass.
  **Must NOT do**: Do not rewrite the old proof or gate artifacts. Do not mark `gemma4_native_real_video_pass` retroactively.

  **Recommended Agent Profile**:
  - Category: `quick` - Reason: bounded evidence artifact.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`git-master`] - Workspace is not a git repo and no commit is requested.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: [7, 8] | Blocked By: []

  **References**:
  - User decision: conversation quote `아냐. 그정도면 capab go야. refactor 진행해`.
  - Prior gate: `.sisyphus/evidence/vid0033-native-proof-gate.json:1-30` - canonical no-go remains unchanged.
  - Final proof: `.sisyphus/evidence/vid0033-gemma4-native-proof.json:219-320` - HTTP 200, visual PASS, audio/cross-modal FAIL.

  **Acceptance Criteria**:
  - [ ] JSON exists with `decision="user_override_capability_go_for_refactor"`.
  - [ ] JSON includes `prior_gate_status="gemma4_capability_no_go"` and `prior_streaming_refactor_allowed=false`.
  - [ ] JSON includes `do_not_mutate_prior_gate=true`.
  - [ ] JSON includes fixed fixture `/home/kio/workspace/gje/vid_0033.mp4`.

  **QA Scenarios**:
  ```
  Scenario: Override evidence is explicit and non-mutating
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && python3 - <<'PY'
import json
override=json.load(open('.sisyphus/evidence/native-streaming-user-override-go.json'))
gate=json.load(open('.sisyphus/evidence/vid0033-native-proof-gate.json'))
assert override['decision']=='user_override_capability_go_for_refactor'
assert override['prior_gate_status']=='gemma4_capability_no_go'
assert override['prior_streaming_refactor_allowed'] is False
assert override['do_not_mutate_prior_gate'] is True
assert gate['status']=='gemma4_capability_no_go'
assert gate['streaming_refactor_allowed'] is False
PY
    Expected: command exits 0.
    Evidence: .sisyphus/evidence/native-streaming-user-override-go.json

  Scenario: Override evidence does not claim proof pass
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && python3 - <<'PY'
import json
d=json.load(open('.sisyphus/evidence/native-streaming-user-override-go.json'))
assert d.get('retroactive_proof_pass') is False
assert 'gemma4_native_real_video_pass' not in d.get('current_authorization_reason','')
PY
    Expected: command exits 0.
    Evidence: .sisyphus/evidence/native-streaming-user-override-go.json
  ```

  **Commit**: NO | Message: `docs(native): record user override for streaming refactor` | Files: [.sisyphus/evidence/native-streaming-user-override-go.json]

- [x] 2. Add Bounded Native MP4 Window Store

  **What to do**: Add `local-infer/src/local_infer/native_media_store.py`. Define immutable `NativeMediaWindow` with `session_id`, `start_ms`, `end_ms`, `duration_ms`, `mime_type`, `sha256`, `host_path`, `file_url`, `size_bytes`. Define `NativeMediaStore` with bounded per-session retention, total bytes limit, base64 validation, MIME validation (`video/mp4` only), safe session directory naming, atomic file write, eviction that removes old files, and `clear(session_id)` cleanup. Config comes from constructor; `create_app` wires env defaults later.
  **Must NOT do**: Do not store transcripts. Do not decode frames. Do not call `audio_analysis.py`. Do not put runtime media under repo-tracked source paths.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: stateful file store with safety and cleanup edge cases.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`frontend-ui-ux`] - No UI work.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: [4, 5, 6, 8] | Blocked By: []

  **References**:
  - Pattern: `local-infer/src/local_infer/frame_store.py:15-55` - bounded per-session store + `RLock`.
  - Pattern: `local-infer/src/local_infer/audio_store.py:25-85` - base64 validation, duration handling, bounded chunks.
  - Existing tests: `local-infer/tests/test_frame_store.py:11-45` - store behavior assertions.

  **Acceptance Criteria**:
  - [ ] `native_media_store.py` exists with `NativeMediaWindow` and `NativeMediaStore`.
  - [ ] Invalid base64, empty body, non-MP4 MIME, `end_ms <= start_ms`, max bytes exceeded, and unsafe session ids fail deterministically with `ValueError`.
  - [ ] Store evicts oldest windows by max count and deletes evicted files.
  - [ ] Sessions are isolated.
  - [ ] Tests use temporary directories only.

  **QA Scenarios**:
  ```
  Scenario: Store preserves bounded rolling MP4 windows
    Tool: Bash
    Steps: cd /home/kio/workspace/gje/local-infer && PYTHONPATH=src uv run --with pytest --with httpx pytest tests/test_native_media_store.py -q
    Expected: tests pass; assertions cover eviction, session isolation, invalid base64, MIME rejection, and file deletion.
    Evidence: .sisyphus/evidence/task-2-native-media-store-pytest.txt

  Scenario: Store never writes to tracked source paths
    Tool: Bash
    Steps: cd /home/kio/workspace/gje/local-infer && PYTHONPATH=src uv run --with pytest --with httpx pytest tests/test_native_media_store.py -q -k runtime_dir
    Expected: tests pass and confirm temp runtime directory is outside src/tests/docs.
    Evidence: .sisyphus/evidence/task-2-native-media-store-runtime-dir.txt
  ```

  **Commit**: NO | Message: `feat(native): add rolling mp4 window store` | Files: [local-infer/src/local_infer/native_media_store.py, local-infer/tests/test_native_media_store.py]

- [x] 3. Add Same-Window Native Audio Transport

  **What to do**: Add `local-infer/src/local_infer/native_audio.py`. It must extract mono 16 kHz WAV bytes from the same uploaded MP4 window for model transport only. Use a small `NativeAudioExtractor` wrapper around `ffmpeg` with configurable binary path, timeout, and max audio seconds (default 30s). Return `NativeInputAudio` containing base64 WAV and `format="wav"`. Fail closed with `ValueError` on missing ffmpeg, extraction timeout, empty audio, or window duration > 30s. Tests should monkeypatch subprocess results; no real ffmpeg dependency is required for unit tests.
  **Must NOT do**: Do not analyze audio content. Do not classify speech/silence. Do not import `audio_analysis.py`. Do not use ASR/VAD/rule fallback. Do not produce transcripts.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: process wrapper and strict guardrail distinction between transport and analysis.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`mem0-cli`] - No CLI memory work.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: [4, 5, 6, 8] | Blocked By: []

  **References**:
  - Final proof precedent: `.sisyphus/evidence/vid0033-window-pack-provenance.json` - same-fixture WAV transport with no transcript/ASR/fallback.
  - vLLM schema finding: `input_audio` shape should be `{"type":"input_audio","input_audio":{"data":"<base64>","format":"wav"}}`.
  - Guardrail: `local-infer/src/local_infer/app.py:150-189` - degraded fallback is separate and must not be reused.

  **Acceptance Criteria**:
  - [ ] `native_audio.py` exists with `NativeAudioExtractor` and `NativeInputAudio`.
  - [ ] Extraction command uses source MP4 file only, output WAV via stdout or temp file, mono 16 kHz PCM.
  - [ ] Tests prove success, missing ffmpeg, timeout, empty output, too-long duration, and subprocess failure behavior.
  - [ ] Static test proves `native_audio.py` does not import `audio_analysis`.

  **QA Scenarios**:
  ```
  Scenario: Same-window audio transport returns input_audio-compatible WAV
    Tool: Bash
    Steps: cd /home/kio/workspace/gje/local-infer && PYTHONPATH=src uv run --with pytest --with httpx pytest tests/test_native_audio.py -q
    Expected: tests pass; successful extraction fixture produces base64 WAV and format wav.
    Evidence: .sisyphus/evidence/task-3-native-audio-pytest.txt

  Scenario: Native audio transport is not fallback analysis
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && python3 - <<'PY'
from pathlib import Path
text=Path('local-infer/src/local_infer/native_audio.py').read_text()
assert 'audio_analysis' not in text
assert 'transcript' not in text.lower()
assert 'vad' not in text.lower()
PY
    Expected: command exits 0.
    Evidence: .sisyphus/evidence/task-3-native-audio-guardrail.txt
  ```

  **Commit**: NO | Message: `feat(native): add same-window input audio transport` | Files: [local-infer/src/local_infer/native_audio.py, local-infer/tests/test_native_audio.py]

- [x] 4. Add Native `video_url` + `input_audio` Payload Builder

  **What to do**: Add `local-infer/src/local_infer/native_payloads.py`. Define `DEFAULT_NATIVE_SYSTEM_PROMPT` for short Korean interview response. Add `build_native_chat_messages(video_file_url, input_audio, prompt, system_prompt)` and `build_native_chat_payload(model, video_file_url, input_audio, prompt, system_prompt, max_tokens, temperature, stream)`. The user message content order is `video_url`, `input_audio`, `text`. Include a helper that returns a payload summary for tests/smoke evidence. Reject empty `video_file_url`, missing `input_audio`, or non-wav `input_audio.format`.
  **Must NOT do**: Do not import `Frame` or `build_chat_payload`. Do not emit `image_url`. Do not include transcript text or ground-truth answers.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: schema correctness is central to avoiding frame fallback contamination.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`mem0-vercel-ai-sdk`] - No Vercel AI SDK work.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: [5, 6, 8] | Blocked By: [2, 3]

  **References**:
  - Existing builder to avoid: `local-infer/src/local_infer/payloads.py:11-57` - emits `image_url` and must not be used by native path.
  - Existing tests style: `local-infer/tests/test_frame_store.py:27-45` - assert content part ordering and type.
  - vLLM schema: `video_url` content part and `input_audio` content part.

  **Acceptance Criteria**:
  - [ ] Native payload contains exactly one `video_url`, one `input_audio`, and one text part in that order.
  - [ ] Native payload contains no `image_url`, no `audio_analysis`, no fallback fields, no transcript keys.
  - [ ] Tests validate `stream=True` and model/max_tokens/temperature fields.
  - [ ] Tests validate invalid inputs raise `ValueError`.

  **QA Scenarios**:
  ```
  Scenario: Native payload uses video_url plus input_audio
    Tool: Bash
    Steps: cd /home/kio/workspace/gje/local-infer && PYTHONPATH=src uv run --with pytest --with httpx pytest tests/test_native_payloads.py -q
    Expected: tests pass and inspect exact OpenAI-compatible content shape.
    Evidence: .sisyphus/evidence/task-4-native-payloads-pytest.txt

  Scenario: Native payload has no frame/fallback markers
    Tool: Bash
    Steps: cd /home/kio/workspace/gje/local-infer && PYTHONPATH=src uv run --with pytest --with httpx pytest tests/test_native_payloads.py -q -k forbidden
    Expected: tests pass; payload summary reports image_url_present=false and fallback_used=false.
    Evidence: .sisyphus/evidence/task-4-native-payloads-forbidden.txt
  ```

  **Commit**: NO | Message: `feat(native): add video and input-audio payload builder` | Files: [local-infer/src/local_infer/native_payloads.py, local-infer/tests/test_native_payloads.py]

- [x] 5. Add Native Window Upload and Generate SSE API

  **What to do**: Extend `local-infer/src/local_infer/app.py` additively. Add the locked `NativeWindowIn`, `NativeGenerateIn`, and `NativeWindowStored` schemas exactly as specified in this plan. Insert native endpoints after the existing `/generate-av-fallback` endpoint and before `return app`, bounded by comments `# Native streaming endpoints begin` and `# Native streaming endpoints end`. Add `POST /v1/native/sessions/{session_id}/windows` to validate/store base64 MP4 windows. Add `POST /v1/native/sessions/{session_id}/generate` to select the latest stored MP4 window, extract same-window input audio, build native payload, stream `client.stream_chat(payload)` via the existing `_sse_event` pattern, and final SSE with `native_media_mode="video_url_plus_input_audio"`, `video_sha256`, `video_url`, `input_audio_present=true`, `fallback_used=false`, `total_ms`. Wire config args into `create_app`: `native_media_store`, `native_audio_extractor`, `native_media_dir`, `native_media_url_prefix`, `max_native_windows_per_session`, `max_native_bytes_per_session`.
  **Must NOT do**: Do not alter existing endpoint behavior except constructor defaults. Do not call `store.get_recent_frames` from native generate. Do not call `audio_store`, `analyze_wav_bytes`, `/audio`, or `/generate-av-fallback` from native path.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: API integration, SSE behavior, and regression-sensitive app changes.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`frontend-ui-ux`] - No UI work.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: [6, 7, 8] | Blocked By: [2, 3, 4]

  **References**:
  - Pattern: `local-infer/src/local_infer/app.py:61-148` - Pydantic models, `_sse_event`, `StreamingResponse`, fake client streaming.
  - Existing fallback separation: `local-infer/src/local_infer/app.py:150-189` - degraded path remains separate.
  - Existing app tests: `local-infer/tests/test_app.py:38-67` - SSE and fake payload capture.

  **Acceptance Criteria**:
  - [ ] `NativeWindowIn` and `NativeGenerateIn` match the locked schema in this plan.
  - [ ] Business-rule validation failures specified in this plan (`stream=false`, wrong MIME, empty decoded MP4, max bytes exceeded, extraction failure, missing native window) are mapped to `HTTPException(status_code=400, detail=...)` instead of leaking 500; Pydantic structural field errors may remain FastAPI 422.
  - [ ] `NativeGenerateIn.stream=false` returns 400 because native generate is SSE-only.
  - [ ] Native endpoint code is bounded by `# Native streaming endpoints begin` and `# Native streaming endpoints end` comments after the fallback endpoint.
  - [ ] Native window upload returns `session_id`, `stored_windows`, `latest_sha256`, `latest_duration_ms`, and `latest_video_url`.
  - [ ] Native generate returns 400 when no native window exists.
  - [ ] Native generate calls fake `client.stream_chat` exactly once with payload containing `video_url` and `input_audio`, no `image_url`.
  - [ ] Native SSE emits `ttft`, `token`, and `final` events.
  - [ ] Existing `tests/test_app.py` and `tests/test_frame_store.py` still pass unchanged.

  **QA Scenarios**:
  ```
  Scenario: Native generate streams with native media payload
    Tool: Bash
    Steps: cd /home/kio/workspace/gje/local-infer && PYTHONPATH=src uv run --with pytest --with httpx pytest tests/test_native_app.py -q
    Expected: tests pass; fake client captured `video_url` + `input_audio`, no `image_url`, and SSE final marks fallback_used=false.
    Evidence: .sisyphus/evidence/task-5-native-app-pytest.txt

  Scenario: Existing frame and fallback routes do not regress
    Tool: Bash
    Steps: cd /home/kio/workspace/gje/local-infer && PYTHONPATH=src uv run --with pytest --with httpx pytest tests/test_app.py tests/test_frame_store.py -q
    Expected: existing tests pass unchanged.
    Evidence: .sisyphus/evidence/task-5-regression-pytest.txt
  ```

  **Commit**: NO | Message: `feat(native): add rolling mp4 streaming endpoints` | Files: [local-infer/src/local_infer/app.py, local-infer/tests/test_native_app.py]

- [x] 6. Add Real `vid_0033.mp4` Native Streaming Smoke Runner

  **What to do**: Add `local-infer/tools/smoke_vid0033_native_stream.py`. It must derive short MP4 windows from `/home/kio/workspace/gje/vid_0033.mp4` with ffmpeg into `/tmp/opencode` or a temp dir, upload them to `/v1/native/sessions/{session_id}/windows`, call `/v1/native/sessions/{session_id}/generate`, parse SSE, and write `.sisyphus/evidence/native-streaming-vid0033-smoke.json`. Include `--in-process-fake-vllm` mode that uses FastAPI TestClient and fake vLLM for deterministic CI; include `--base-url` live mode for manual/runtime smoke. Evidence must include source SHA, uploaded windows, native endpoint names, captured payload summary when fake, response excerpt, timings, and forbidden-path checks.
  **Must NOT do**: Do not call `/frames`, `/generate`, `/audio`, `/generate-av-fallback`, ASR/VAD, or fallback analysis. Do not use synthetic media.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: end-to-end smoke plus artifact generation.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`frontend-ui-ux`] - No UI work.

  **Parallelization**: Can Parallel: YES | Wave 4 | Blocks: [8] | Blocked By: [5]

  **References**:
  - Fixture metadata: `.sisyphus/evidence/vid0033-media-metadata.json:1-36` - locked path/SHA and media properties.
  - Existing SSE parser for tests: `local-infer/tests/test_app.py:170-175` - parse SSE events.
  - Existing vLLM stream pattern: `local-infer/src/local_infer/vllm_client.py:20-28`.

  **Acceptance Criteria**:
  - [ ] Smoke runner supports `--source`, `--out`, `--session-id`, `--prompt`, `--in-process-fake-vllm`, and optional `--base-url`.
  - [ ] Smoke evidence asserts `source_path=="/home/kio/workspace/gje/vid_0033.mp4"` and source SHA matches metadata.
  - [ ] Fake smoke exits 0 without a live Gemma4 server.
  - [ ] Evidence has `video_url_present=true`, `input_audio_present=true`, `image_url_present=false`, `fallback_used=false`, `response_non_empty=true`.

  **QA Scenarios**:
  ```
  Scenario: In-process smoke proves native streaming structure on real fixture
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && python3 local-infer/tools/smoke_vid0033_native_stream.py --source /home/kio/workspace/gje/vid_0033.mp4 --out .sisyphus/evidence/native-streaming-vid0033-smoke.json --in-process-fake-vllm --session-id native-smoke-vid0033
    Expected: exits 0 and evidence reports native endpoints, real fixture SHA, video_url_present=true, input_audio_present=true, image_url_present=false, fallback_used=false.
    Evidence: .sisyphus/evidence/native-streaming-vid0033-smoke.json

  Scenario: Smoke fails clearly when source file is missing
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && python3 local-infer/tools/smoke_vid0033_native_stream.py --source /home/kio/workspace/gje/missing.mp4 --out .sisyphus/evidence/native-streaming-missing-source.json --in-process-fake-vllm; test $? -ne 0
    Expected: command proves missing source is rejected and writes/prints deterministic error.
    Evidence: .sisyphus/evidence/native-streaming-missing-source.json
  ```

  **Commit**: NO | Message: `test(native): add vid0033 native streaming smoke` | Files: [local-infer/tools/smoke_vid0033_native_stream.py, .sisyphus/evidence/native-streaming-*.json]

- [x] 7. Update Docs and Runbook for User-Override Native Streaming Path

  **What to do**: Update docs to describe the new native path and the override semantics. Modify `local-infer/README.md`, `local-infer/docs/API_CONTRACT.md`, `local-infer/docs/ARCHITECTURE.md`, `local-infer/docs/RUNBOOK.md`, `README.md`, and `INFERENCE_PIPELINE.md` only as needed. Docs must show request/response examples for `/v1/native/sessions/{id}/windows` and `/v1/native/sessions/{id}/generate`, runtime env vars, Docker/vLLM mount guidance for `LOCAL_INFER_NATIVE_MEDIA_DIR` and `LOCAL_INFER_NATIVE_MEDIA_URL_PREFIX`, smoke command, and a clear note that prior proof gate remains no-go but user override authorizes refactor.
  **Must NOT do**: Do not erase the prior no-go history. Do not claim fallback paths are native success. Do not document native path as replacing existing frame path.

  **Recommended Agent Profile**:
  - Category: `writing` - Reason: documentation and runbook clarity.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`mem0`] - No memory SDK work.

  **Parallelization**: Can Parallel: YES | Wave 4 | Blocks: [8] | Blocked By: [1, 5]

  **References**:
  - Current API docs to update: `local-infer/docs/API_CONTRACT.md:6-12` - currently says native endpoints unavailable; must change after implementation.
  - Current architecture docs: `local-infer/docs/ARCHITECTURE.md:34-40` - no-go stop-state; must add override semantics.
  - Current runbook verification style: `local-infer/docs/RUNBOOK.md:63-79`.

  **Acceptance Criteria**:
  - [ ] Docs include `user_override_capability_go_for_refactor`.
  - [ ] API docs include native upload/generate examples.
  - [ ] Runbook includes smoke command and full pytest command.
  - [ ] Docs say `/frames` path still exists but is not the native streaming refactor path.
  - [ ] Docs say `/audio` and `/generate-av-fallback` remain degraded fallback and not native success.

  **QA Scenarios**:
  ```
  Scenario: Docs expose override and native endpoint contract
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && grep -R -E "user_override_capability_go_for_refactor|/v1/native/sessions/.*/windows|/v1/native/sessions/.*/generate|video_url|input_audio" README.md INFERENCE_PIPELINE.md local-infer/README.md local-infer/docs
    Expected: grep finds override, native endpoints, and native payload terms.
    Evidence: .sisyphus/evidence/task-7-docs-grep.txt

  Scenario: Docs still reject fallback as native success
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && grep -R -E "fallback.*not.*native|generate-av-fallback.*not.*native|audio_analysis.*not" local-infer/README.md local-infer/docs README.md INFERENCE_PIPELINE.md
    Expected: grep finds explicit fallback-not-native statements.
    Evidence: .sisyphus/evidence/task-7-fallback-guardrail-grep.txt
  ```

  **Commit**: NO | Message: `docs(native): document user override streaming path` | Files: [README.md, INFERENCE_PIPELINE.md, local-infer/README.md, local-infer/docs/*]

- [x] 8. Run Full Verification, Guardrails, and Final Review Prep

  **What to do**: Run all tests and static guardrails, capture evidence, and prepare final review wave. Create `.sisyphus/evidence/native-streaming-refactor-final.json` summarizing override decision, implemented endpoints, tests, smoke output, docs status, and remaining caveats. Run LSP diagnostics on changed Python/Markdown where available. Confirm no task-specific vLLM containers remain. Do not mark final review items complete until review agents approve.
  **Must NOT do**: Do not skip smoke. Do not ignore stale docs. Do not start live vLLM unless explicitly needed for optional live smoke; fake/in-process smoke is mandatory and sufficient for structural CI.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: cross-cutting verification and evidence consolidation.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`git-master`] - No commit requested and workspace is not a git repo.

  **Parallelization**: Can Parallel: NO | Wave 5 | Blocks: [final verification] | Blocked By: [1, 2, 3, 4, 5, 6, 7]

  **References**:
  - Final evidence style: `.sisyphus/evidence/task-10-final-state.md` - concise stop-state evidence pattern.
  - Current passing test baseline: `local-infer/README.md:111-118` - `14 passed` before native refactor.
  - Docker cleanup expectation: `local-infer/docs/RUNBOOK.md:81-99`.

  **Acceptance Criteria**:
  - [ ] Full `local-infer` pytest passes.
  - [ ] Native smoke evidence exists and passes consistency assertions.
  - [ ] Static guardrail check finds no forbidden native-path imports/calls.
  - [ ] Docs grep checks pass.
  - [ ] Final evidence JSON exists with test command outputs and caveats.

  **QA Scenarios**:
  ```
  Scenario: Static guardrail forbids fallback contamination in native path
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && python3 - <<'PY'
from pathlib import Path
app = Path('local-infer/src/local_infer/app.py').read_text()
native_payloads = Path('local-infer/src/local_infer/native_payloads.py').read_text()
native_audio = Path('local-infer/src/local_infer/native_audio.py').read_text()
native_store = Path('local-infer/src/local_infer/native_media_store.py').read_text()
for text, name in [(native_payloads,'native_payloads'), (native_audio,'native_audio'), (native_store,'native_media_store')]:
    for forbidden in ['audio_analysis', 'generate_av_fallback', 'build_chat_payload', 'FrameStore']:
        assert forbidden not in text, f'{name} contains {forbidden}'
    compact = ''.join(text.split())
    assert '"type":"image_url"' not in compact, f'{name} emits image_url part'
    assert "'type':'image_url'" not in compact, f'{name} emits image_url part'
assert '# Native streaming endpoints begin' in app
assert '# Native streaming endpoints end' in app
native_section = app.split('# Native streaming endpoints begin', 1)[1].split('# Native streaming endpoints end', 1)[0]
for forbidden in ['analyze_wav_bytes', 'audio_store', 'get_recent_frames', 'build_chat_payload', 'generate_av_fallback']:
    assert forbidden not in native_section, f'native app section contains {forbidden}'
PY
    Expected: command exits 0.
    Evidence: .sisyphus/evidence/task-8-static-guardrail.txt

  ```

  ```
  Scenario: Full verification gate passes
    Tool: Bash
    Steps: cd /home/kio/workspace/gje/local-infer && PYTHONPATH=src uv run --with pytest --with httpx pytest tests -q
    Expected: all tests pass.
    Evidence: .sisyphus/evidence/task-8-full-pytest.txt

  Scenario: Native smoke evidence consistency
    Tool: Bash
    Steps: cd /home/kio/workspace/gje && python3 - <<'PY'
import json
d=json.load(open('.sisyphus/evidence/native-streaming-vid0033-smoke.json'))
assert d['source_path']=='/home/kio/workspace/gje/vid_0033.mp4'
assert d['video_url_present'] is True
assert d['input_audio_present'] is True
assert d['image_url_present'] is False
assert d['fallback_used'] is False
assert d['response_non_empty'] is True
PY
    Expected: command exits 0.
    Evidence: .sisyphus/evidence/native-streaming-vid0033-smoke.json

  Scenario: No task-specific vLLM containers remain
    Tool: Bash
    Steps: docker ps --format '{{.Names}}' | grep -E 'vllm-gemma4.*task|native-streaming' && exit 1 || exit 0
    Expected: command exits 0.
    Evidence: .sisyphus/evidence/task-8-docker-cleanup.txt
  ```

  **Commit**: NO | Message: `test(native): verify user override streaming refactor` | Files: [.sisyphus/evidence/native-streaming-refactor-final.json, .sisyphus/evidence/task-8-*]

## Final Verification Wave (MANDATORY — after ALL implementation tasks)
> 4 review agents run in PARALLEL. ALL must APPROVE by returning PASS/APPROVE with no blocking issues. Completion is agent-executed: F1-F4 may be checked only after the review artifacts show all four approvals.
> **Never mark F1-F4 as checked before review agents approve.**
- [x] F1. Plan Compliance Audit — oracle
- [x] F2. Code Quality Review — unspecified-high
- [x] F3. Native Runtime QA — unspecified-high (pytest + smoke; no UI)
- [x] F4. Scope Fidelity Check — deep

## Commit Strategy
- Environment metadata says this workspace is not a git repo, so plan tasks use `Commit: NO`.
- If executor later enters a git repo, commit only after user approval and after inspecting `git status`, `git diff`, and recent log.

## Success Criteria
- Native streaming refactor exists as additive `/v1/native/...` path.
- Real `vid_0033.mp4` smoke proves structure uses native MP4 window transport and same-window input audio.
- Existing frame/fallback endpoints remain functional and clearly non-native-success.
- Prior no-go proof artifacts remain unchanged and are contextualized by user override evidence.
- All tests, docs checks, smoke checks, and final review agents pass.
