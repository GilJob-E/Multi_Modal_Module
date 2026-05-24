# Learnings

## 2026-05-22 Start Work
- Active work is `native-streaming-refactor-user-override`, selected after user said the prior accepted Gemma4 E4B native media result is capability-go for refactor.
- Prior canonical proof artifacts remain unchanged: `gemma4_capability_no_go`, `streaming_refactor_allowed=false`.
- New execution authorization is separate: `user_override_capability_go_for_refactor`.
- Native path must be additive under `/v1/native/sessions/{id}/...` and must not replace `/frames` or `/generate`.
- Native route must use MP4 window `video_url` plus same-window `input_audio` WAV transport; no `image_url[]`, no `/audio`, no `/generate-av-fallback`, no `audio_analysis.py`, no ASR/VAD/rule fallback.
- Existing patterns: app endpoints use FastAPI/Pydantic/`StreamingResponse`; tests use `FakeVllmClient` to capture payloads; stores use bounded per-session `deque` plus `RLock`.

## 2026-05-22 Task 3 Native Audio Transport
- Added `local_infer.native_audio` as a transport-only ffmpeg wrapper: MP4 window in, mono 16 kHz PCM WAV bytes out as `input_audio` base64 with `format="wav"`.
- Native audio extraction fails closed before model transport on missing ffmpeg, timeout, nonzero ffmpeg exit, empty stdout, and windows longer than the default 30 seconds.
- Targeted pytest needs `uv run --with pytest pytest ...` in this environment because plain `pytest`/`python3 -m pytest` is not installed globally.

## 2026-05-22 User Override Evidence
- Recorded user override authorization as a separate artifact while preserving the locked gate artifact unchanged.
- Accepted native proof facts remain E4B, HTTP 200, visual PASS, and audio/cross-modal FAIL from the quiet-tail misclassification.
- Fixed fixture for this override record is `/home/kio/workspace/gje/vid_0033.mp4`.

## 2026-05-22 Task 2 Native Media Store
- Added `NativeMediaStore` as a stdlib-only file-backed rolling MP4 window store with per-session `deque`, `RLock`, safe session IDs, deterministic `{start}-{end}-{sha}.mp4` names, constructor-configured runtime dir, and URL prefix mapping.
- Validation rejects non-MP4 MIME, invalid base64, empty decoded bytes, invalid timestamps, windows over 30000 ms, unsafe session IDs, and decoded bytes over configured limits before writing media files.
- Tests cover max-window eviction, oldest cross-session byte-budget eviction, file deletion, session isolation, invalid inputs, oversized bytes, clear cleanup, tmp_path runtime dir use, and immutable windows.

## 2026-05-22 Task 2 Verification Fix
- Fixed duplicate MP4 path collisions by adding a per-store monotonic suffix to filenames while preserving the decoded media SHA-256 in `NativeMediaWindow.sha256`.
- Regression coverage now proves same-session duplicate eviction and cross-session duplicate clear keep retained duplicate files readable with correct total byte accounting.

## 2026-05-22 Task 2 Runtime Dir Evidence
- Captured the missing runtime-dir QA artifact at `.sisyphus/evidence/task-2-native-media-store-runtime-dir.txt` using the exact `-k runtime_dir` pytest scenario; result was `1 passed, 14 deselected`.

## 2026-05-22 Task 4 Native Payload Builder
- Added a pure `local_infer.native_payloads` helper that builds system/user chat messages with exactly `video_url`, `input_audio`, then `text` for the native path.
- Native payload summary reports structural guardrail flags/counts, including `video_url_present`, `input_audio_present`, `image_url_present`, and `fallback_used`, for Task 5 smoke/evidence reuse.
- Task 4 pytest evidence is captured at `.sisyphus/evidence/task-4-native-payloads-pytest.txt` and `.sisyphus/evidence/task-4-native-payloads-forbidden.txt`.

## 2026-05-22 Task 5 Native App Endpoints
- Added additive `/v1/native/sessions/{session_id}/windows` and `/v1/native/sessions/{session_id}/generate` routes bounded by the required native endpoint comments.
- Native generate uses only the latest stored MP4 window, extracts same-window WAV input audio before streaming, builds the Task 4 native payload, and emits `ttft`, `token`, and `final` SSE events with `fallback_used=false`.
- Task 5 evidence is captured at `.sisyphus/evidence/task-5-native-app-pytest.txt` and `.sisyphus/evidence/task-5-regression-pytest.txt`.

## 2026-05-22 Task 6 Native Streaming Smoke Runner
- Added `local-infer/tools/smoke_vid0033_native_stream.py` to derive real 3s MP4 windows from the locked `vid_0033.mp4` fixture with ffmpeg and upload only to native `/v1/native/...` endpoints.
- Mandatory fake mode uses FastAPI `TestClient`, fake vLLM, and fake native audio extraction for deterministic structural CI while still exercising real MP4 window upload/generate SSE.
- Evidence artifacts are `.sisyphus/evidence/native-streaming-vid0033-smoke.json` and `.sisyphus/evidence/native-streaming-missing-source.json`; python3 runner auto-reexecs through `uv run` if FastAPI dependencies are absent globally.

## 2026-05-22 Task 7 Docs Update
- Updated workspace and local-infer docs to present the additive `/v1/native/sessions/{id}/windows` and `/v1/native/sessions/{id}/generate` path as authorized by `user_override_capability_go_for_refactor`, while preserving `.sisyphus/evidence/vid0033-native-proof-gate.json` as `gemma4_capability_no_go` with `streaming_refactor_allowed=false`.
- Documented native payload shape as `video_url` plus same-window WAV `input_audio` plus text, with no `image_url[]` on the native path.
- Captured docs grep evidence at `.sisyphus/evidence/task-7-docs-grep.txt` and fallback guardrail evidence at `.sisyphus/evidence/task-7-fallback-guardrail-grep.txt`.

## 2026-05-22 Task 8 Final Verification
- Full local-infer pytest passed with 54 tests and evidence in `.sisyphus/evidence/task-8-full-pytest.txt`.
- Static native guardrail passed and found no fallback/frame/image contamination in the native path.
- Smoke evidence consistency, current docs grep checks, docker cleanup, and diagnostics all passed; final summary is `.sisyphus/evidence/native-streaming-refactor-final.json`.

## 2026-05-22 Task 8 Parent Verification Fix
- Added `local-infer/tests/test_native_forbidden_paths.py` so the exact plan Definition of Done targeted native command has a real guardrail file to execute.
- The new guardrail test statically checks native modules and the bounded native endpoint block for fallback/frame/audio-analysis contamination while confirming the locked native routes are present.
- Refreshed Task 8 targeted and full pytest evidence: targeted native pytest passed with 43 tests and full pytest passed with 57 tests.
