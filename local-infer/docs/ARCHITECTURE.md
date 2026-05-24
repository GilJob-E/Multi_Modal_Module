# local-infer 아키텍처

## 목표

`google/gemma-4-31B-it`를 vLLM 위에서 구동하고, 화상통화 서비스가 붙이기 쉬운 **저지연 video-native 추론 모듈**을 제공한다.

## 범위

포함:

- 세션별 JPEG 프레임 수집
- 최근 N프레임 기반 multimodal vLLM 호출
- Additive native rolling MP4 window 수집
- Native `video_url` plus same-window `input_audio` vLLM 호출
- token-level SSE 스트리밍
- TTFT/total latency 계측 이벤트

제외:

- STT/TTS
- Gemini Live 접목
- GilJob 프론트/백엔드 통합
- Cloudflare 제거
- ASR/VAD/rule fallback을 native success로 승격하는 방식

## 레이턴시 철학

이 모듈이 계승하는 중간보고서의 핵심은 다른 기능이 아니라 **TTFT 최소화를 위한 선행 처리 철학**이다.

- 사용자가 말하는 동안 비디오 입력을 계속 수신한다.
- 입력을 요청 시점까지 방치하지 않고 미리 샘플링/정규화/버퍼링한다.
- VAD 또는 end-of-turn 트리거 시점에는 이미 최근 시각 컨텍스트가 준비되어 있어야 한다.
- 최종 목표는 턴 종료 후 업로드, 디코드, 샘플링, 프리필, 생성을 순차 실행하는 것이 아니라, 턴 진행 중 앞단 작업을 최대한 당겨서 첫 토큰 지연을 LLM 본체 하한에 가깝게 만드는 것이다.

현재 구현은 두 API 경계를 둔다. 기존 raw JPEG frame buffer path는 계속 유지된다. User override native path는 rolling MP4 window를 따로 저장하고 latest window를 native media payload로 보낸다.

## Native proof gate와 user override

Canonical gate status는 `.sisyphus/evidence/vid0033-native-proof-gate.json` 기준 `gemma4_capability_no_go`이며 `streaming_refactor_allowed=false`다. 고정 real proof fixture는 `/home/kio/workspace/gje/vid_0033.mp4`다.

Final accepted native request는 `google/gemma-4-E4B-it`, `video_plus_window_pack_soundtrack`, prompt version `window_pack_native_v4`, real MP4 fixture, same-fixture window-pack WAV를 사용했고 vLLM은 HTTP 200을 반환했다. Visual check는 통과했고 12-17s mid-window speech-like activity도 감지됐다. Proof gate는 48.176-50.286s quiet-tail window를 Gemma4가 `speech`로 분류해 audio와 cross-modal checks가 실패했기 때문에 no-go로 남는다.

Streaming refactor is allowed only by the separate user override evidence `.sisyphus/evidence/native-streaming-user-override-go.json`, with `decision=user_override_capability_go_for_refactor`. The user explicitly judged the accepted E4B native media result sufficient for engineering refactor. This architecture does not mutate the prior gate and does not claim fallback/native proof success incorrectly.

Evidence:

- `.sisyphus/evidence/vid0033-gemma4-native-proof.json`
- `.sisyphus/evidence/vid0033-native-proof-gate.json`
- `.sisyphus/evidence/native-streaming-user-override-go.json`
- `.sisyphus/evidence/vid0033-window-pack-provenance.json`

## Audio route state after Tasks 4 through 10

The current selected audio route is `native-no-go`, not Gemma/Qwen success. `.sisyphus/evidence/task-6-route-decision.json` records `selected_route=native-no-go`, `native_route_status=no-go`, `fallback_enabled=true`, and fallback `native_success=false`.

The architecture therefore has three separate layers:

- Frame-only visual baseline: the 31B path uses `/v1/sessions/{id}/frames` and `/v1/sessions/{id}/generate` with `image_url[]`. It is not native audio, and current `google/gemma-4-31B-it` MP4 `video_url` AAC behavior is not proof of native audio understanding.
- Attempted native audio route: Gemma4 E4B/E2B explicit WAV `input_audio` probes failed in Task 4. Qwen2.5-Omni did not pass all required probes in Task 5, even though one `cross_modal_event` check passed. Task 7 implementation and Task 8 native integration tests were blocked and skipped because no selected route exists.
- Degraded local fallback: `/v1/sessions/{session_id}/audio` stores WAV chunks for local cue analysis. `/v1/sessions/{session_id}/generate-av-fallback` combines that analysis with recent frame presence and emits `native_success=false`. It is degraded local audio-analysis fallback, not native ASR and not native multimodal inference.

The `/v1/native/sessions/{session_id}/windows` and `/v1/native/sessions/{session_id}/generate` flow remains a user-override engineering path for `video_url` plus same-window `input_audio` payload shape. It does not convert the legacy native audio-understanding plan into a pass.

Evidence: `.sisyphus/evidence/task-4-gemma4-native-probe.json`, `.sisyphus/evidence/task-4-gemma4-no-go.md`, `.sisyphus/evidence/task-5-qwen-native-probe.json`, `.sisyphus/evidence/task-5-qwen-no-go.md`, `.sisyphus/evidence/task-6-route-decision.json`, `.sisyphus/evidence/task-6-route-decision.md`, `.sisyphus/evidence/task-7-blocked.md`, `.sisyphus/evidence/task-8-blocked.md`, and `.sisyphus/evidence/task-10-asr-fallback.md`.

## 데이터 흐름

Existing frame path:

```text
클라이언트/통합 어댑터
  ├─ POST /v1/sessions/{id}/frames
  │       ↓
  │   FrameStore(session_id -> bounded deque)
  │
  └─ POST /v1/sessions/{id}/generate
          ↓
      payloads.build_chat_payload()
          ↓
      image_url[] content parts
          ↓
      VllmClient -> http://localhost:8000/v1/chat/completions(stream=True)
          ↓
      local-infer SSE: ttft/token/final
```

Degraded local audio-analysis fallback:

```text
클라이언트/통합 어댑터
  ├─ POST /v1/sessions/{id}/audio
  │       ↓
  │   AudioStore keeps bounded WAV chunks
  │
  └─ POST /v1/sessions/{id}/generate-av-fallback
          ↓
      deterministic local audio_analysis plus frame presence
          ↓
      local-infer SSE final: fallback_mode=degraded_local_audio_analysis, native_success=false
```

Native user override path:

```text
클라이언트/통합 어댑터
  ├─ POST /v1/native/sessions/{id}/windows
  │       ↓
  │   NativeMediaStore writes bounded MP4 window files
  │       ↓
  │   latest_video_url from LOCAL_INFER_NATIVE_MEDIA_URL_PREFIX
  │
  └─ POST /v1/native/sessions/{id}/generate
          ↓
      NativeAudioExtractor extracts WAV from the same stored MP4 window
          ↓
      native_payloads.build_native_chat_payload()
          ↓
      video_url + input_audio + text content parts, no image_url[]
          ↓
      VllmClient -> http://localhost:8000/v1/chat/completions(stream=True)
          ↓
      local-infer SSE: ttft/token/final
```

## 핵심 설계

- **Frame push 모델 유지**: `/frames`와 `/generate`는 계속 존재한다. 이 경로는 native streaming refactor path가 아니다.
- **Native MP4 window 모델 추가**: `/v1/native/sessions/{id}/windows`는 base64 MP4 window를 저장한다.
- **Native generate는 latest window만 사용**: `/v1/native/sessions/{id}/generate`는 latest stored MP4 window의 `video_url`과 same-window WAV `input_audio`를 보낸다.
- **No frame substitution**: Native path는 `image_url[]`를 쓰지 않는다.
- **No fallback success**: `/audio`와 `/generate-av-fallback`은 degraded fallback path다. `generate-av-fallback` is not native success, fallback paths are not native proof, and `audio_analysis` is not native media understanding.
- **고정 system prompt**: vLLM prefix cache hit 확률을 높인다.
- **짧은 출력**: 면접 후속 질문/관찰은 `max_tokens`를 낮게 유지해 total latency를 줄인다.
- **vLLM 직접 노출 금지**: 통합 대상은 local-infer API만 보게 한다.

## Native payload shape

`native_payloads.build_native_chat_payload()` creates OpenAI-compatible chat content with this order:

```json
[
  {"type": "video_url", "video_url": {"url": "file:///...mp4"}},
  {"type": "input_audio", "input_audio": {"data": "<base64 wav>", "format": "wav"}},
  {"type": "text", "text": "..."}
]
```

The audio is same-window transport from the uploaded MP4. It is not ASR, VAD, transcript, or `audio_analysis`.

## Runtime media visibility

`LOCAL_INFER_NATIVE_MEDIA_DIR` controls where local-infer writes native MP4 window files. `LOCAL_INFER_NATIVE_MEDIA_URL_PREFIX` controls the `video_url` string sent to vLLM. Default local behavior is `file://{LOCAL_INFER_NATIVE_MEDIA_DIR}`.

When vLLM runs in Docker, the media directory must be mounted so vLLM can read the same files. If a later vLLM configuration uses `file://`, configure the container path and allowed local media access for that runtime.

## 코드 맵

- `src/local_infer/app.py`: FastAPI 앱, native and non-native endpoints, SSE 이벤트 생성
- `src/local_infer/frame_store.py`: 세션별 bounded in-memory frame buffer
- `src/local_infer/native_media_store.py`: bounded MP4 window file store
- `src/local_infer/native_audio.py`: same-window WAV `input_audio` extraction
- `src/local_infer/native_payloads.py`: `video_url` plus `input_audio` payload 생성
- `src/local_infer/payloads.py`: existing `image_url[]` payload 생성
- `src/local_infer/vllm_client.py`: vLLM `/v1/models`, `/v1/chat/completions` 호출
- `src/local_infer/vllm_stream.py`: vLLM SSE byte stream에서 content delta만 추출
