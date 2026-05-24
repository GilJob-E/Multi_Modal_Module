# gje

실시간 멀티모달 면접 시스템 프로젝트를 위한 작업 공간입니다.

현재 이 폴더의 핵심 산출물은 **로컬 Gemma4/vLLM 기반 최소지연 video-native 추론 파이프라인 모듈**입니다.

## 현재 Gemma4 native proof gate와 user override

최종 canonical proof gate는 여전히 `.sisyphus/evidence/vid0033-native-proof-gate.json`입니다. 이 파일의 상태는 `gemma4_capability_no_go`이며 `streaming_refactor_allowed=false`입니다. 이 기록은 통과로 바꾸지 않습니다.

새 refactor는 별도 evidence인 `.sisyphus/evidence/native-streaming-user-override-go.json`의 `user_override_capability_go_for_refactor` 결정으로 진행합니다. 사용자는 accepted E4B native media 결과를 engineering refactor에 충분한 capability signal로 판단했습니다. 따라서 prior no-go history는 보존하고, 구현 권한만 user override로 분리합니다.

기존 `/v1/sessions/{id}/frames`와 `/v1/sessions/{id}/generate` 경로는 계속 존재하지만 native streaming refactor path가 아닙니다. `/v1/sessions/{id}/audio`와 `/v1/sessions/{id}/generate-av-fallback`은 degraded fallback 경로이며 fallback paths are not native success. `audio_analysis` is not native proof.

## 현재 audio understanding 상태

현재 문서의 기준 상태는 Task 6 route lock이다. `.sisyphus/evidence/task-6-route-decision.json`은 `selected_route=native-no-go`, `native_route_status=no-go`, `fallback_enabled=true`를 기록한다. 따라서 현재 검증된 층은 다음 셋으로 나눈다.

- Frame-only visual baseline: `google/gemma-4-31B-it` 경로는 `/v1/sessions/{id}/frames`와 `/v1/sessions/{id}/generate`에서 최근 JPEG `image_url[]`만 쓰는 visual baseline이다. MP4 `video_url` 안의 AAC 동작이나 frame-only 결과를 native audio understanding으로 부르지 않는다.
- Native audio route attempts: Task 4 Gemma4 E4B/E2B explicit `input_audio` WAV probes failed, and Task 5 Qwen did not pass all required probes. Qwen `cross_modal_event` passing alone is not a route pass. Task 6 selected `native-no-go`.
- Degraded local fallback: Task 10 documents `/v1/sessions/{session_id}/audio` and `/v1/sessions/{session_id}/generate-av-fallback` as deterministic local WAV cue analysis plus frame presence. It emits `native_success=false` and is not native ASR, transcript ASR, or native multimodal inference.

Task 7 native-success implementation was blocked and skipped, so no `/generate-av-native` endpoint was added. Task 8 native integration tests were blocked and skipped because no selected native route exists. The separate `/v1/native/sessions/{session_id}/windows` and `/v1/native/sessions/{session_id}/generate` endpoints remain a user-override engineering path for native media payload shape, not proof that the legacy audio-understanding native route passed.

Current no-go and fallback evidence stays visible: `.sisyphus/evidence/task-4-gemma4-native-probe.json`, `.sisyphus/evidence/task-4-gemma4-no-go.md`, `.sisyphus/evidence/task-5-qwen-native-probe.json`, `.sisyphus/evidence/task-5-qwen-no-go.md`, `.sisyphus/evidence/task-6-route-decision.json`, `.sisyphus/evidence/task-6-route-decision.md`, `.sisyphus/evidence/task-7-blocked.md`, `.sisyphus/evidence/task-8-blocked.md`, and `.sisyphus/evidence/task-10-asr-fallback.md`.

## 빠른 진입점

- 전체 인덱스: `INFERENCE_PIPELINE.md`
- 채택 모듈: `local-infer/`
- Native API 계약: `local-infer/docs/API_CONTRACT.md`
- Native runbook: `local-infer/docs/RUNBOOK.md`
- Phase 0 벤치: `local-infer/experiments/phase0/README.md`
- SGLang No-Go 기록: `sglang/EXPERIMENT_LOG.md`
- 원본 벤치/샘플: `video-test/`

## 추론 엔진 결정

실시간 추론 엔진으로 **vLLM 채택** (2026-05-20). SGLang 이전은 검토했으나 No-Go.

- vLLM: `google/gemma-4-31B-it` 원본 + online fp8 + TP=2
- SGLang fp8: 2×4090 24GB에서 메모리/실용 성능 한계
- SGLang AWQ: Gemma4 vision tower compressed-tensors 지원 미완성으로 기동 실패

## 입력 인터페이스 결정

현재 구현은 두 입력 경로를 함께 둡니다.

- 기존 low-latency frame path: `/v1/sessions/{id}/frames`로 JPEG를 쌓고 `/v1/sessions/{id}/generate`가 최근 `image_url[]` 프레임을 보냅니다.
- User override native path: `/v1/native/sessions/{id}/windows`로 rolling MP4 window를 올리고 `/v1/native/sessions/{id}/generate`가 `video_url`과 같은 window에서 뽑은 `input_audio` WAV를 보냅니다. 이 native path는 `image_url[]`를 쓰지 않습니다.

## 디렉터리

```text
local-infer/    # FastAPI local inference module
sglang/         # SGLang 실험/No-Go 기록
video-test/     # 기존 vLLM/Gemma4 벤치 스크립트와 샘플
.hermes/plans/  # 계획 문서
```

## 외부 의존 경로

- `~/hf_cache/`: Gemma 4 모델 캐시 및 vLLM 컨테이너 볼륨 마운트 대상.
- Docker 컨테이너: `vllm-gemma4`
- Native runtime media dir: `LOCAL_INFER_NATIVE_MEDIA_DIR`, 기본값 `/tmp/gje-local-infer-native-media`
- Native media URL prefix: `LOCAL_INFER_NATIVE_MEDIA_URL_PREFIX`, 기본값 `file://{LOCAL_INFER_NATIVE_MEDIA_DIR}`

## GPU 운영 원칙

모델을 안 쓸 때는 컨테이너를 stop하고 VRAM 해제를 확인합니다.

```bash
docker stop vllm-gemma4
nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader
```
