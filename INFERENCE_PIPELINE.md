# GilJob 로컬 Video-Native 추론 파이프라인 정리

이 문서는 `~/workspace/gje` 안의 **로컬 Gemma4/vLLM 최소지연 추론 모듈** 관련 핵심 결과와 파일 위치를 한눈에 보기 위한 인덱스다.

## 현재 Gemma4 native proof gate와 user override

최종 canonical Gemma4 native proof gate는 `.sisyphus/evidence/vid0033-native-proof-gate.json`이다. 상태는 `gemma4_capability_no_go`이고 `streaming_refactor_allowed=false`다. 고정 real proof fixture는 `/home/kio/workspace/gje/vid_0033.mp4`다. E4B는 real fixture native media request를 HTTP 200으로 받았지만 48.176-50.286s quiet-tail window를 `speech`로 분류해 audio/cross-modal checks가 실패했다.

이 no-go 기록은 그대로 보존한다. 새 native streaming refactor는 `.sisyphus/evidence/native-streaming-user-override-go.json`의 `decision=user_override_capability_go_for_refactor`로 진행한다. 사용자가 accepted E4B native media 결과를 engineering refactor에 충분한 capability signal로 판단했기 때문이다. 이 결정은 prior proof gate를 pass로 바꾸지 않고, `gemma4_native_real_video_pass`를 retroactive로 주장하지 않는다.

기준 evidence:

- `.sisyphus/evidence/vid0033-gemma4-native-proof.json`
- `.sisyphus/evidence/vid0033-native-proof-gate.json`
- `.sisyphus/evidence/native-streaming-user-override-go.json`
- `.sisyphus/evidence/task-10-final-state.md`

## 현재 native audio route lock

Task 6 is the current authority for audio understanding route selection. `.sisyphus/evidence/task-6-route-decision.json` records `selected_route=native-no-go`, `native_route_status=no-go`, and `fallback_enabled=true`. This means the current implementation must keep three layers separate.

1. Frame-only visual baseline: `/v1/sessions/{id}/frames` plus `/v1/sessions/{id}/generate` sends recent JPEG frames as `image_url[]`. It is a visual baseline for `google/gemma-4-31B-it`, not native audio. Current `google/gemma-4-31B-it` MP4 `video_url` AAC behavior is not native audio understanding.
2. Attempted native audio routes: Task 4 showed Gemma4 E4B and E2B reached vLLM readiness, then rejected all explicit `input_audio` WAV probes. Task 5 showed Qwen2.5-Omni did not pass all required local native probes. Qwen `cross_modal_event` passed, but required audio-positive, no-audio ablation, and Korean phrase checks failed, so Qwen did not pass.
3. Degraded local audio-analysis fallback: Task 10 provides `/v1/sessions/{session_id}/audio` and `/v1/sessions/{session_id}/generate-av-fallback`. This is deterministic local WAV cue analysis plus recent frame presence, not transcript ASR and not native multimodal inference. The final event reports `fallback_mode=degraded_local_audio_analysis` and `native_success=false`.

Task 7 native-success implementation was blocked and skipped because no selected native route exists. Task 8 native integration testing was blocked and skipped for the same reason. `/v1/native/sessions/{session_id}/windows` and `/v1/native/sessions/{session_id}/generate` remain the user-override native media payload engineering path, not proof that the legacy audio-understanding plan passed.

Evidence for this state: `.sisyphus/evidence/task-4-gemma4-native-probe.json`, `.sisyphus/evidence/task-4-gemma4-no-go.md`, `.sisyphus/evidence/task-5-qwen-native-probe.json`, `.sisyphus/evidence/task-5-qwen-no-go.md`, `.sisyphus/evidence/task-6-route-decision.json`, `.sisyphus/evidence/task-6-route-decision.md`, `.sisyphus/evidence/task-7-blocked.md`, `.sisyphus/evidence/task-8-blocked.md`, and `.sisyphus/evidence/task-10-asr-fallback.md`.

## 범위

- 담당 범위: **최소지연 video-native 로컬 추론 파이프라인 모듈**
- 제외 범위: Cloudflare 제거, GilJob 프론트/백엔드 통합, Gemini Live 접목, STT/TTS
- 채택 엔진: **vLLM + `google/gemma-4-31B-it` + online fp8 + TP=2**
- 구현 언어: **Python/FastAPI**

## 계승할 레이턴시 철학

중간보고서의 다른 구현 범위는 현재 담당 범위 밖이다. 다만 아래 **레이턴시 철학**만 local-infer 설계 원칙으로 계승한다.

> 사용자가 말하는 동안 시각 입력을 미리 수신, 디코드, 샘플링, 전처리해 두고, VAD/end-of-turn 트리거가 발생하는 순간에는 LLM 프리필 또는 이에 준하는 준비가 즉시 시작되도록 만든다.

즉 목표는 “요청 시점에 처음 영상을 처리”하는 구조가 아니라:

```text
실시간 입력 수신 중 선행 처리
→ frame/keyframe/summary/prefix-ready 상태 유지
→ VAD 또는 턴 종료 시점에 최소 추가 계산으로 generate 시작
→ TTFT 체감 지연 최소화
```

## 현재 결정 사항

1. **SGLang은 No-Go**
   - 동일 원본 모델 fp8 경로는 2×4090 24GB에서 메모리/성능 문제가 큼.
   - AWQ 4bit 경로는 SGLang의 Gemma4 vision tower compressed-tensors 지원 미완성으로 막힘.
   - 기록: `sglang/EXPERIMENT_LOG.md`

2. **기존 frame path는 계속 유지**
   - `/v1/sessions/{id}/frames`와 `/v1/sessions/{id}/generate`는 JPEG `image_url[]` 기반 SSE 경로다.
   - 이 경로는 native streaming refactor path가 아니다.

3. **User override native path가 추가됨**
   - MP4 upload: `POST /v1/native/sessions/{id}/windows`
   - Native generate: `POST /v1/native/sessions/{id}/generate`
   - Payload shape: `video_url` plus same-window `input_audio` WAV plus text.
   - Native path sends no `image_url[]`.

4. **Fallback guardrail**
    - `/v1/sessions/{id}/audio`와 `/v1/sessions/{id}/generate-av-fallback`은 degraded fallback path다.
    - Task 10 verifies this as degraded local audio-analysis fallback with `native_success=false`.
    - `generate-av-fallback` is not native success, fallback paths are not native proof, and `audio_analysis` is not native media understanding.

## Native endpoint summary

`POST /v1/native/sessions/{id}/windows` stores a rolling MP4 window.

```json
{
  "start_ms": 12000,
  "end_ms": 17000,
  "video_mp4_base64": "<base64 mp4 bytes>",
  "mime_type": "video/mp4"
}
```

`POST /v1/native/sessions/{id}/generate` streams SSE from the latest native MP4 window.

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

Final SSE includes `native_media_mode`, `video_sha256`, `video_url`, `input_audio_present`, `fallback_used=false`, and `total_ms`.

## 디렉터리 맵

```text
~/workspace/gje/
├── INFERENCE_PIPELINE.md
├── README.md
├── local-infer/
│   ├── README.md
│   ├── pyproject.toml
│   ├── src/local_infer/
│   │   ├── app.py
│   │   ├── native_media_store.py
│   │   ├── native_audio.py
│   │   ├── native_payloads.py
│   │   ├── frame_store.py
│   │   ├── payloads.py
│   │   ├── vllm_client.py
│   │   └── vllm_stream.py
│   ├── tests/
│   ├── docs/
│   │   ├── ARCHITECTURE.md
│   │   ├── API_CONTRACT.md
│   │   ├── RUNBOOK.md
│   │   └── DECISIONS.md
│   ├── tools/
│   └── experiments/phase0/README.md
├── sglang/
└── video-test/
```

## 빠른 검증

```bash
cd ~/workspace/gje/local-infer
PYTHONPATH=src uv run --with pytest --with httpx pytest tests/test_native_media_store.py tests/test_native_audio.py tests/test_native_payloads.py tests/test_native_app.py tests/test_native_forbidden_paths.py -q
PYTHONPATH=src uv run --with pytest --with httpx pytest tests -q
```

Native smoke command:

```bash
cd /home/kio/workspace/gje
python3 local-infer/tools/smoke_vid0033_native_stream.py --source /home/kio/workspace/gje/vid_0033.mp4 --out .sisyphus/evidence/native-streaming-vid0033-smoke.json --in-process-fake-vllm --session-id native-smoke-vid0033
```

vLLM을 켠 상태에서 모듈 실행:

```bash
cd ~/workspace/gje/local-infer
PYTHONPATH=src VLLM_BASE_URL=http://localhost:8000 uvicorn local_infer.app:app --host 0.0.0.0 --port 8080
```

## GPU 운영 원칙

작업 종료 후에는 반드시 vLLM 컨테이너를 중지하고 VRAM이 비었는지 확인한다.

```bash
docker stop vllm-gemma4
nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader
```

정상 종료 기준: GPU0/GPU1 메모리 한 자릿수 MiB, util 0%.
