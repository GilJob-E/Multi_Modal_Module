# local-infer API Contract

Base URL 예시: `http://localhost:8080`

## Proof gate, user override, and path boundaries

Canonical gate status remains `gemma4_capability_no_go`; `streaming_refactor_allowed=false`. The canonical gate file is `.sisyphus/evidence/vid0033-native-proof-gate.json`. It stays no-go and is not edited to pass.

The additive native streaming API exists because `.sisyphus/evidence/native-streaming-user-override-go.json` records `decision=user_override_capability_go_for_refactor`. The user explicitly judged the accepted E4B native media result sufficient for engineering refactor. This does not claim `gemma4_native_real_video_pass` retroactively.

Existing `/v1/sessions/{session_id}/frames` and `/v1/sessions/{session_id}/generate` still exist. They are the JPEG `image_url[]` path and are not the native streaming refactor path. Existing `/v1/sessions/{session_id}/audio` and `/v1/sessions/{session_id}/generate-av-fallback` are degraded fallback paths. `generate-av-fallback` is not native success, fallback paths are not native proof, and `audio_analysis` is not native media understanding.

Task 6 route lock is authoritative for audio understanding: `.sisyphus/evidence/task-6-route-decision.json` records `selected_route=native-no-go`, `native_route_status=no-go`, `fallback_enabled=true`, and fallback `native_success=false`. The current 31B frame-only visual baseline is not native audio. Task 4 and Task 5 native audio attempts did not pass, Task 7 native-success implementation was blocked and skipped, and Task 8 native integration testing was blocked and skipped. Task 10 adds only degraded local audio-analysis fallback.

Endpoint layers:

- Frame-only visual baseline: `POST /v1/sessions/{session_id}/frames` and `POST /v1/sessions/{session_id}/generate`.
- Degraded local audio-analysis fallback: `POST /v1/sessions/{session_id}/audio` and `POST /v1/sessions/{session_id}/generate-av-fallback`, always non-native and `native_success=false` when fallback results are emitted.
- User-override native media payload path: `POST /v1/native/sessions/{session_id}/windows` and `POST /v1/native/sessions/{session_id}/generate`, not proof that the legacy native audio-understanding route passed.

No API in this contract should be read as a passing native audio route. Current no-go evidence remains `.sisyphus/evidence/task-4-gemma4-native-probe.json`, `.sisyphus/evidence/task-4-gemma4-no-go.md`, `.sisyphus/evidence/task-5-qwen-native-probe.json`, `.sisyphus/evidence/task-5-qwen-no-go.md`, `.sisyphus/evidence/task-6-route-decision.md`, `.sisyphus/evidence/task-7-blocked.md`, `.sisyphus/evidence/task-8-blocked.md`, and `.sisyphus/evidence/task-10-asr-fallback.md`.

## GET `/v1/health`

vLLM 연결 상태와 모델 정보를 확인한다.

응답 예시:

```json
{
  "ok": true,
  "model": "google/gemma-4-31B-it",
  "vllm": {"object": "list", "data": []}
}
```

## POST `/v1/sessions/{session_id}/frames`

세션에 JPEG 프레임을 push한다. 권장 주기: 1fps.

요청:

```json
{
  "timestamp_ms": 1000,
  "frame_jpeg_base64": "..."
}
```

응답:

```json
{
  "session_id": "demo",
  "stored_frames": 5
}
```

## POST `/v1/sessions/{session_id}/generate`

최근 N프레임을 사용해 vLLM multimodal streaming 생성을 수행한다. 이 endpoint는 native MP4 window path가 아니다.

요청:

```json
{
  "prompt": "지원자의 표정과 자세를 짧게 묘사하고 후속 질문 한 개를 해줘.",
  "n_frames": 5,
  "max_tokens": 128,
  "temperature": 0.2
}
```

SSE 응답:

```text
data: {"type":"ttft","ttft_ms":149.4}

data: {"type":"token","text":"현재"}

data: {"type":"final","text":"현재 ...","frames_used":5,"total_ms":1208.0}
```

## POST `/v1/sessions/{session_id}/audio`

WAV audio chunks can be stored for the degraded fallback route. This is not native success and is not part of `/v1/native`.

Request:

```json
{
  "timestamp_ms": 12000,
  "audio_wav_base64": "...",
  "duration_ms": 2000
}
```

This endpoint feeds deterministic local WAV cue analysis only. It does not create a native audio route, transcript ASR route, hosted ASR route, or native multimodal inference route.

Fields:

- `timestamp_ms`: integer, `>=0`.
- `audio_wav_base64`: non-empty base64 WAV bytes.
- `duration_ms`: integer, `>=0`, used by the fallback windowing logic.

## POST `/v1/sessions/{session_id}/generate-av-fallback`

This route combines recent frames with deterministic local WAV analysis. `generate-av-fallback` is not native success. The final event may contain `fallback_mode=degraded_local_audio_analysis`, `native_success=false`, `audio_analysis`, `frames_used`, and `audio_used_ms`. `audio_analysis` is not native proof.

Request:

```json
{
  "prompt": "지원자의 현재 답변과 태도를 짧게 보고 후속 질문 하나를 해줘.",
  "n_frames": 5,
  "audio_window_ms": 2000,
  "max_tokens": 128,
  "temperature": 0.2
}
```

Fields:

- `prompt`: non-empty string.
- `n_frames`: integer `1..30`, default `5`.
- `audio_window_ms`: integer `1..10000`, default `2000`.
- `max_tokens`: integer `1..1024`, default `128`.
- `temperature`: float `0.0..2.0`, default `0.2`.

## POST `/v1/native/sessions/{session_id}/windows`

Stores one rolling MP4 window for the user-override native media payload path. The request body is JSON, not multipart. This endpoint is not proof that a native audio route passed Task 6.

Request:

```json
{
  "start_ms": 12000,
  "end_ms": 17000,
  "video_mp4_base64": "<base64 mp4 bytes>",
  "mime_type": "video/mp4"
}
```

Fields:

- `start_ms`: integer, `>=0`.
- `end_ms`: integer, must be `> start_ms`. Duration must be `<=30000`.
- `video_mp4_base64`: non-empty base64 MP4 bytes.
- `mime_type`: exactly `video/mp4`.

Response:

```json
{
  "session_id": "demo",
  "stored_windows": 1,
  "latest_sha256": "...",
  "latest_duration_ms": 5000,
  "latest_video_url": "file:///native-media/demo/<sha>.mp4"
}
```

## POST `/v1/native/sessions/{session_id}/generate`

Streams SSE from the latest native MP4 window for the user-override engineering path. This endpoint is SSE-only. `stream=false` returns 400. It sends a native media payload shape, but it does not supersede `native-no-go` for the legacy audio-understanding plan.

Request:

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

Fields:

- `prompt`: non-empty string.
- `system_prompt`: optional string, defaults to native Korean interviewer prompt.
- `max_tokens`: integer `1..1024`.
- `temperature`: float `0.0..2.0`.
- `model`: optional string. `null` uses `LOCAL_INFER_MODEL`.
- `stream`: must be `true`.

Native payload shape sent to vLLM:

```json
[
  {"type": "video_url", "video_url": {"url": "file:///...mp4"}},
  {"type": "input_audio", "input_audio": {"data": "<base64 wav>", "format": "wav"}},
  {"type": "text", "text": "지원자의 현재 답변과 태도를 짧게 보고 후속 질문 하나를 해줘."}
]
```

The `input_audio` is extracted from the same uploaded MP4 window. The native path sends no `image_url[]`.

Final SSE event:

```text
data: {"type":"final","text":"...","native_media_mode":"video_url_plus_input_audio","video_sha256":"...","video_url":"file:///...mp4","input_audio_present":true,"fallback_used":false,"total_ms":123.4}
```

Required final fields are `native_media_mode`, `video_sha256`, `video_url`, `input_audio_present`, `fallback_used=false`, and `total_ms`.

## Native runtime media configuration

- `LOCAL_INFER_NATIVE_MEDIA_DIR`: host directory where uploaded MP4 windows are stored. Default: `/tmp/gje-local-infer-native-media`.
- `LOCAL_INFER_NATIVE_MEDIA_URL_PREFIX`: URL prefix written into `video_url`. Default: `file://{LOCAL_INFER_NATIVE_MEDIA_DIR}`.

For Docker/vLLM, the media files must be visible to vLLM. Mount `LOCAL_INFER_NATIVE_MEDIA_DIR` into the vLLM container, keep the path stable with the URL prefix, and configure allowed local media file access if that vLLM deployment requires it for `file://` URLs.

## 통합팀이 지켜야 할 점

- Use `/v1/native/sessions/{id}/windows` plus `/v1/native/sessions/{id}/generate` only when testing the user override native path.
- Use `/v1/sessions/{id}/frames` plus `/v1/sessions/{id}/generate` for the existing frame path.
- Do not treat `/audio`, `/generate-av-fallback`, `audio_analysis`, transcript, or frame-only output as native success.
- 첫 호출은 prefill 때문에 느릴 수 있다. 동일 세션 warm path가 실제 목표 latency다.
- 서버는 GPU를 오래 점유하므로 사용하지 않을 때 vLLM 컨테이너를 stop해야 한다.
