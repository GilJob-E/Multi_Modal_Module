# 결정 사항과 근거

## D1. 엔진은 vLLM으로 확정

- 결정: SGLang이 아니라 vLLM 사용.
- 근거: vLLM은 동일 2×RTX4090에서 Gemma4 31B fp8을 안정적으로 구동했고 warm TTFT 0.3s 이하를 확인했다.
- SGLang 기록: `../../sglang/EXPERIMENT_LOG.md`

## D2. 기존 low-latency 입력 방식은 누적 프레임 `image_url[]`

- 결정: 기존 `/v1/sessions/{id}/frames`와 `/v1/sessions/{id}/generate` 경로는 JPEG frame push + 최근 N프레임 호출로 유지한다.
- 근거:
  - `video_url` 30초 전체 영상 cold TTFT 약 7.98s.
  - `image_url[]` N=3~5 warm TTFT 0.17~0.24s.
- Phase 0 기록: `../experiments/phase0/README.md`

## D3. 구현 언어는 Python/FastAPI

- 결정: 빠른 작성과 vLLM 생태계 정합을 위해 Python/FastAPI.
- 근거: 기존 벤치 스크립트가 Python이고, requests/stream parsing 재사용이 쉽다.

## D4. API는 세션 기반

- 결정: 기존 path는 `/v1/sessions/{id}/frames`로 프레임을 쌓고 `/generate`에서 최근 N개를 사용한다. Native override path는 `/v1/native/sessions/{id}/windows`로 MP4 window를 쌓고 `/v1/native/sessions/{id}/generate`에서 latest window를 사용한다.
- 근거: 실시간 면접은 입력이 지속적으로 들어오고, 생성 트리거는 VAD/턴 종료/텍스트 도착 시점에 발생한다.

## D5. GPU 위생 규칙

- 결정: 실험/사용 종료 후 vLLM 컨테이너 stop 및 `nvidia-smi` 확인.
- 근거: 사용자의 GPU 운영 원칙. 모델을 안 쓸 때 VRAM을 점유하지 않는다.

## D6. 중간보고서에서는 레이턴시 철학만 계승

- 결정: 중간보고서의 여러 구성 요소 중 현재 local-infer가 직접 챙길 것은 **TTFT 최소화를 위한 선행 처리 철학**뿐이다.
- 범위 밖: Cloudflare/GilJob 통합, Gemini Live 접목, 프론트/아바타, STT/TTS, AVI2026 baseline, RAG.
- 계승할 핵심: 사용자가 말하는 동안 비디오 입력을 미리 수신, 샘플링, 버퍼링하고, VAD/end-of-turn 시점에 LLM 프리필 또는 generate가 즉시 시작되게 한다.
- 다음 검증: end-of-turn cold 대비 periodic prefill, append-only prefix, sliding-window 방식의 TTFT/VRAM/throughput 비교.

## D7. User override native streaming path

- 결정: `.sisyphus/evidence/native-streaming-user-override-go.json`의 `user_override_capability_go_for_refactor`에 따라 additive native path를 문서화한다.
- 근거: 사용자가 accepted E4B native media 결과를 engineering refactor에 충분한 capability signal로 판단했다.
- 보존 사항: `.sisyphus/evidence/vid0033-native-proof-gate.json`은 계속 `gemma4_capability_no_go`, `streaming_refactor_allowed=false`다.
- Native payload: latest MP4 window `video_url` plus same-window WAV `input_audio` plus text. No `image_url[]` on `/v1/native/sessions/{id}/generate`.
- Guardrail: `/audio` and `/generate-av-fallback` remain degraded fallback paths. `generate-av-fallback` is not native success, fallback paths are not native proof, and `audio_analysis` is not native media understanding.

## D8. Audio understanding route remains native-no-go

- 결정: Task 6 route lock selects `native-no-go`. No Gemma4 or Qwen route is selected for native audio understanding.
- 근거: `.sisyphus/evidence/task-6-route-decision.json` records `selected_route=native-no-go`, `native_route_status=no-go`, `fallback_enabled=true`, and fallback `native_success=false`.
- Gemma4 evidence: Task 4 shows E4B and E2B reached vLLM readiness, then all explicit `input_audio` WAV probes failed. Evidence: `.sisyphus/evidence/task-4-gemma4-native-probe.json` and `.sisyphus/evidence/task-4-gemma4-no-go.md`.
- Qwen evidence: Task 5 shows primary GPTQ failed local load, and alternate 3B did not pass all required probes. `cross_modal_event` passing is not enough because required audio-positive, no-audio ablation, and Korean phrase checks failed. Evidence: `.sisyphus/evidence/task-5-qwen-native-probe.json` and `.sisyphus/evidence/task-5-qwen-no-go.md`.
- Downstream impact: Task 7 native-success implementation was blocked and skipped, so no `/generate-av-native` endpoint should be documented. Task 8 native integration testing was blocked and skipped. Evidence: `.sisyphus/evidence/task-7-blocked.md` and `.sisyphus/evidence/task-8-blocked.md`.
- Fallback decision: Task 10 documents only degraded local audio-analysis fallback. `/v1/sessions/{session_id}/audio` and `/v1/sessions/{session_id}/generate-av-fallback` use deterministic local WAV cue analysis plus frame presence and emit `native_success=false`. Evidence: `.sisyphus/evidence/task-10-asr-fallback.md`.
- Boundary: the current 31B frame-only visual baseline is not native audio, and current `google/gemma-4-31B-it` MP4 `video_url` AAC behavior is not native audio understanding. `/v1/native/sessions/{session_id}/windows` and `/v1/native/sessions/{session_id}/generate` remain a user-override native media payload engineering path, not a pass for the legacy audio-understanding plan.
