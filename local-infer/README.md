# GilJob local-infer

로컬 Gemma4/vLLM 기반 **최소지연 video-native 추론 파이프라인** 모듈.

## 한 줄 결론

기존 low-latency 경로는 **1fps JPEG frame push + 최근 N프레임 `image_url[]` 생성**으로 유지한다. User override refactor로 별도 native 경로도 추가됐다. 이 경로는 rolling MP4 window를 `video_url`로 보내고 같은 window에서 뽑은 WAV `input_audio`를 함께 보낸다.

## 현재 proof gate와 user override

Canonical proof gate는 `.sisyphus/evidence/vid0033-native-proof-gate.json`이다. 현재 gate status는 `gemma4_capability_no_go`이고 `streaming_refactor_allowed=false`다. 고정 real proof fixture는 `/home/kio/workspace/gje/vid_0033.mp4`다.

최종 accepted native request는 `google/gemma-4-E4B-it`, real fixture, native media, vLLM HTTP 200 조건을 만족했다. Visual check는 통과했고 12-17s mid-window speech도 감지했다. 하지만 final quiet-tail check가 실패했다. Gemma4가 48.176-50.286s window를 `speech`로 분류해서 audio check와 cross-modal check가 실패했다.

이 no-go history는 지우지 않는다. Native streaming refactor는 `.sisyphus/evidence/native-streaming-user-override-go.json`의 `decision=user_override_capability_go_for_refactor` 때문에 진행한다. 사용자가 accepted E4B native media 결과를 engineering refactor에 충분하다고 명시적으로 판단했기 때문이다. 이 문서는 prior proof gate가 now passes라고 말하지 않으며 `gemma4_native_real_video_pass`를 retroactive로 주장하지 않는다.

Evidence:

- `.sisyphus/evidence/vid0033-gemma4-native-proof.json`
- `.sisyphus/evidence/vid0033-native-proof-gate.json`
- `.sisyphus/evidence/native-streaming-user-override-go.json`
- `.sisyphus/evidence/vid0033-window-pack-provenance.json`

## Current native audio route status

Task 6 locks the current audio route decision to `native-no-go`. The machine source is `.sisyphus/evidence/task-6-route-decision.json`, with `selected_route=native-no-go`, `native_route_status=no-go`, `fallback_enabled=true`, and fallback `native_success=false`.

Keep these layers separate:

- Frame-only visual baseline: `/v1/sessions/{id}/frames` and `/v1/sessions/{id}/generate` use recent JPEG frames as `image_url[]`. This is the current 31B visual baseline, not native audio. Do not call MP4 `video_url` AAC behavior on current `google/gemma-4-31B-it` native audio understanding.
- Attempted native audio route: Task 4 Gemma4 E4B/E2B explicit `input_audio` WAV probes failed. Task 5 Qwen primary GPTQ failed to load, and alternate 3B had `all_required_passed=false`; `cross_modal_event` alone did not select Qwen. Task 7 and Task 8 native-success work stayed blocked and skipped.
- Degraded local audio-analysis fallback: Task 10 verified `/v1/sessions/{session_id}/audio` and `/v1/sessions/{session_id}/generate-av-fallback` as local WAV cue analysis plus frame presence. This is degraded, non-native, and reports `native_success=false`.

The user-override endpoints `/v1/native/sessions/{session_id}/windows` and `/v1/native/sessions/{session_id}/generate` are still documented for native media payload engineering. They do not prove the legacy native audio-understanding plan passed.

Evidence: `.sisyphus/evidence/task-4-gemma4-native-probe.json`, `.sisyphus/evidence/task-4-gemma4-no-go.md`, `.sisyphus/evidence/task-5-qwen-native-probe.json`, `.sisyphus/evidence/task-5-qwen-no-go.md`, `.sisyphus/evidence/task-6-route-decision.json`, `.sisyphus/evidence/task-6-route-decision.md`, `.sisyphus/evidence/task-7-blocked.md`, `.sisyphus/evidence/task-8-blocked.md`, and `.sisyphus/evidence/task-10-asr-fallback.md`.

## 범위

포함:

- 기존 프레임 수집
- 기존 최근 N프레임 기반 vLLM multimodal streaming 호출
- Native rolling MP4 window upload
- Native `video_url` plus same-window `input_audio` payload
- TTFT 계측
- SSE 출력

제외:

- Cloudflare 제거
- GilJob 프론트/백엔드 통합
- Gemini Live 직/병렬 접목
- STT/TTS
- ASR/VAD/rule fallback을 native success로 쓰는 방식

## Guardrails

`/v1/sessions/{id}/frames`와 `/v1/sessions/{id}/generate`는 계속 존재하지만 native streaming refactor path가 아니다. 이 기존 경로는 `image_url[]` frame path다.

`/v1/sessions/{id}/audio`와 `/v1/sessions/{id}/generate-av-fallback`도 계속 존재한다. 이들은 degraded fallback 경로다. `generate-av-fallback` is not native success, fallback paths are not native proof, and `audio_analysis` is not native media understanding.

Native path는 `/v1/native/sessions/{id}/generate` 안에서 `image_url[]`를 보내지 않는다. Payload는 `video_url`, same-window `input_audio` WAV, text 순서다.

## 레이턴시 철학

중간보고서에서 현재 모듈이 계승할 부분은 다른 통합/프론트/평가 내용이 아니라 **TTFT 최소화를 위한 선행 처리 원칙**이다.

```text
사용자 발화 중 비디오 입력 선행 수신/샘플링/버퍼링
→ VAD/end-of-turn 시점에 프리필 또는 generate 즉시 시작
→ 첫 토큰 지연 최소화
```

현재 MVP는 HTTP frame buffer path와 additive native MP4 window path를 함께 둔다. 다음 단계는 periodic/append-only prefill이 실제 end-of-turn TTFT를 줄이는지 벤치하는 것이다.

## 주요 문서

- 전체 인덱스: `../INFERENCE_PIPELINE.md`
- 아키텍처: `docs/ARCHITECTURE.md`
- API 계약: `docs/API_CONTRACT.md`
- 실행/운영: `docs/RUNBOOK.md`
- 결정 기록: `docs/DECISIONS.md`
- Phase 0 벤치: `experiments/phase0/README.md`
- Interaction Models 조사: `research/interaction-models-thinking-machines.md`

## 코드 구조

```text
src/local_infer/
├── app.py                  # FastAPI endpoints + SSE
├── frame_store.py          # session frame buffer
├── native_media_store.py   # bounded rolling MP4 window store
├── native_audio.py         # same-window WAV input_audio extraction
├── native_payloads.py      # video_url + input_audio payload builder
├── payloads.py             # image_url[] payload builder
├── vllm_client.py          # vLLM OpenAI-compatible client
└── vllm_stream.py          # SSE parser
```

## 실행

```bash
cd ~/workspace/gje/local-infer
PYTHONPATH=src VLLM_BASE_URL=http://localhost:8000 uvicorn local_infer.app:app --host 0.0.0.0 --port 8080
```

환경변수:

```bash
export VLLM_BASE_URL=http://localhost:8000
export LOCAL_INFER_MODEL=google/gemma-4-31B-it
export LOCAL_INFER_NATIVE_MEDIA_DIR=/tmp/gje-local-infer-native-media
export LOCAL_INFER_NATIVE_MEDIA_URL_PREFIX=file:///tmp/gje-local-infer-native-media
```

`LOCAL_INFER_NATIVE_MEDIA_DIR` is where local-infer writes rolling MP4 windows. `LOCAL_INFER_NATIVE_MEDIA_URL_PREFIX` is the URL prefix placed into the native `video_url` payload. In local non-container runs, the default `file://{LOCAL_INFER_NATIVE_MEDIA_DIR}` is enough.

For Docker/vLLM, media files must be visible inside the vLLM container at the same path or through an agreed mapped path. If later `file://` access is used with vLLM in a container, mount the media directory into the container and configure any required allowed local media path setting for that vLLM deployment. Do not point `video_url` at a host-only path that the container cannot read.

## API 빠른 예시

프레임 push:

```bash
curl -X POST http://localhost:8080/v1/sessions/demo/frames -H 'content-type: application/json' -d '{"timestamp_ms":1000,"frame_jpeg_base64":"..."}'
```

기존 frame streaming 생성:

```bash
curl -N -X POST http://localhost:8080/v1/sessions/demo/generate -H 'content-type: application/json' -d '{"prompt":"지원자의 표정과 자세를 짧게 묘사하고 후속 질문 한 개를 해줘.","n_frames":5,"max_tokens":128}'
```

Native MP4 window upload:

```bash
curl -X POST http://localhost:8080/v1/native/sessions/demo/windows -H 'content-type: application/json' -d '{"start_ms":12000,"end_ms":17000,"video_mp4_base64":"<base64 mp4 bytes>","mime_type":"video/mp4"}'
```

Native streaming generate:

```bash
curl -N -X POST http://localhost:8080/v1/native/sessions/demo/generate -H 'content-type: application/json' -d '{"prompt":"지원자의 현재 답변과 태도를 짧게 보고 후속 질문 하나를 해줘.","system_prompt":"당신은 한국어 화상 면접관입니다...","max_tokens":128,"temperature":0.2,"model":null,"stream":true}'
```

Native final SSE 출력:

```text
data: {"type":"final","text":"...","native_media_mode":"video_url_plus_input_audio","video_sha256":"...","video_url":"file:///...mp4","input_audio_present":true,"fallback_used":false,"total_ms":123.4}
```

## 테스트

Native targeted tests:

```bash
cd ~/workspace/gje/local-infer
PYTHONPATH=src uv run --with pytest --with httpx pytest tests/test_native_media_store.py tests/test_native_audio.py tests/test_native_payloads.py tests/test_native_app.py tests/test_native_forbidden_paths.py -q
```

Full test suite:

```bash
cd ~/workspace/gje/local-infer
PYTHONPATH=src uv run --with pytest --with httpx pytest tests -q
```

Native structural smoke command:

```bash
cd /home/kio/workspace/gje
python3 local-infer/tools/smoke_vid0033_native_stream.py --source /home/kio/workspace/gje/vid_0033.mp4 --out .sisyphus/evidence/native-streaming-vid0033-smoke.json --in-process-fake-vllm --session-id native-smoke-vid0033
```

## 종료 시 GPU 언로드

```bash
docker stop vllm-gemma4
nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader
```
