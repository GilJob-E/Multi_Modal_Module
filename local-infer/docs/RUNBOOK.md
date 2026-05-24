# local-infer Runbook

## 1. vLLM 시작

기존 컨테이너가 있으면:

```bash
docker start vllm-gemma4
```

새로 만들 때는 `~/workspace/gje/sglang/launch-configs/vllm_baseline.sh` 참고.

Ready 확인:

```bash
python3 - <<'PY'
import requests
r = requests.get('http://localhost:8000/v1/models', timeout=10)
print(r.status_code)
print(r.text[:500])
PY
```

## 2. Native media mount 확인

Native path는 local-infer가 MP4 window files를 `LOCAL_INFER_NATIVE_MEDIA_DIR`에 쓰고, vLLM payload에는 `LOCAL_INFER_NATIVE_MEDIA_URL_PREFIX`로 만든 `video_url`을 넣는다.

기본값:

```bash
export LOCAL_INFER_NATIVE_MEDIA_DIR=/tmp/gje-local-infer-native-media
export LOCAL_INFER_NATIVE_MEDIA_URL_PREFIX=file:///tmp/gje-local-infer-native-media
```

Local non-container vLLM에서는 기본 `file://` prefix가 충분하다. Docker/vLLM에서는 media files must be visible to vLLM. `LOCAL_INFER_NATIVE_MEDIA_DIR`를 vLLM container에 mount하고, container가 읽는 path와 `LOCAL_INFER_NATIVE_MEDIA_URL_PREFIX`가 맞는지 확인한다. `file://` usage later requires allowed local media path or mount configuration in that vLLM deployment.

## 3. local-infer 실행

```bash
cd ~/workspace/gje/local-infer
PYTHONPATH=src VLLM_BASE_URL=http://localhost:8000 uvicorn local_infer.app:app --host 0.0.0.0 --port 8080
```

## 4. 테스트

Native targeted tests:

```bash
cd /home/kio/workspace/gje/local-infer
PYTHONPATH=src uv run --with pytest --with httpx pytest tests/test_native_media_store.py tests/test_native_audio.py tests/test_native_payloads.py tests/test_native_app.py tests/test_native_forbidden_paths.py -q
```

Full pytest command from Definition of Done:

```bash
cd /home/kio/workspace/gje/local-infer
PYTHONPATH=src uv run --with pytest --with httpx pytest tests -q
```

## 5. Existing frame smoke flow

1. `/v1/health` 확인
2. `/v1/sessions/demo/frames`로 프레임 3~5개 push
3. `/v1/sessions/demo/generate` 호출
4. SSE에서 `ttft`, `token`, `final` 이벤트 확인

This path still exists but is not the native streaming refactor path.

## 6. Native smoke flow

1. `POST /v1/native/sessions/{id}/windows`로 MP4 window를 push한다.
2. `POST /v1/native/sessions/{id}/generate`를 `stream=true`로 호출한다.
3. SSE에서 `ttft`, `token`, `final` 이벤트를 확인한다.
4. Final event has `native_media_mode`, `video_sha256`, `video_url`, `input_audio_present`, `fallback_used=false`, and `total_ms`.

Required structural smoke command:

```bash
cd /home/kio/workspace/gje
python3 local-infer/tools/smoke_vid0033_native_stream.py --source /home/kio/workspace/gje/vid_0033.mp4 --out .sisyphus/evidence/native-streaming-vid0033-smoke.json --in-process-fake-vllm --session-id native-smoke-vid0033
```

The smoke is structural and can use fake in-process vLLM. It must show `video_url`, same-window `input_audio`, no `image_url[]`, `fallback_used=false`, and non-empty SSE response.

## 7. Proof gate and user override

Canonical proof gate remains `.sisyphus/evidence/vid0033-native-proof-gate.json` with `gemma4_capability_no_go` and `streaming_refactor_allowed=false`. The fixed real proof fixture is `/home/kio/workspace/gje/vid_0033.mp4`.

The final accepted native request used `google/gemma-4-E4B-it`, the real fixture, native media, and vLLM returned HTTP 200. Visual check passed, and the 12-17s mid-window speech-like activity was detected. The gate did not pass because Gemma4 classified the 48.176-50.286s quiet-tail window as `speech`, causing audio and cross-modal checks to fail.

The native streaming refactor proceeds because `.sisyphus/evidence/native-streaming-user-override-go.json` records `decision=user_override_capability_go_for_refactor`. The user explicitly judged the accepted E4B native media result sufficient for engineering refactor. Do not claim the prior proof gate now passes.

Fallback guardrail: `/audio` and `/generate-av-fallback` remain degraded fallback paths. `generate-av-fallback` is not native success, fallback paths are not native proof, and `audio_analysis` is not native media understanding.

Task 6 is the current route lock for audio understanding. It selected `native-no-go`, with `native_route_status=no-go`, `fallback_enabled=true`, and fallback `native_success=false`. Do not operate the system as if Gemma4 or Qwen passed native audio.

Operationally, keep three flows separate:

1. Frame-only visual baseline: use `/v1/sessions/{id}/frames` and `/v1/sessions/{id}/generate`. This is recent JPEG `image_url[]` context for `google/gemma-4-31B-it`, not native audio. MP4 `video_url` AAC behavior on current 31B is not native audio understanding.
2. User-override native media payload path: use `/v1/native/sessions/{id}/windows` and `/v1/native/sessions/{id}/generate` only when exercising the engineering path. It is not proof that Task 6 passed.
3. Degraded local audio-analysis fallback: use `/v1/sessions/{session_id}/audio` and `/v1/sessions/{session_id}/generate-av-fallback`. Expect `fallback_mode=degraded_local_audio_analysis` and `native_success=false`.

Task 7 native-success implementation was blocked and skipped, so do not look for `/generate-av-native`. Task 8 native integration tests were blocked and skipped because no selected native route exists.

Evidence:

- `.sisyphus/evidence/vid0033-gemma4-native-proof.json`
- `.sisyphus/evidence/vid0033-native-proof-gate.json`
- `.sisyphus/evidence/native-streaming-user-override-go.json`
- `.sisyphus/evidence/vid0033-window-pack-provenance.json`
- `.sisyphus/evidence/task-4-gemma4-native-probe.json`
- `.sisyphus/evidence/task-4-gemma4-no-go.md`
- `.sisyphus/evidence/task-5-qwen-native-probe.json`
- `.sisyphus/evidence/task-5-qwen-no-go.md`
- `.sisyphus/evidence/task-6-route-decision.json`
- `.sisyphus/evidence/task-6-route-decision.md`
- `.sisyphus/evidence/task-7-blocked.md`
- `.sisyphus/evidence/task-8-blocked.md`
- `.sisyphus/evidence/task-10-asr-fallback.md`

Task 7 docs verification commands:

```bash
cd /home/kio/workspace/gje
grep -R -E "user_override_capability_go_for_refactor|/v1/native/sessions/.*/windows|/v1/native/sessions/.*/generate|video_url|input_audio" README.md INFERENCE_PIPELINE.md local-infer/README.md local-infer/docs
grep -R -E "fallback.*not.*native|generate-av-fallback.*not.*native|audio_analysis.*not" local-infer/README.md local-infer/docs README.md INFERENCE_PIPELINE.md
```

## 8. 종료/GPU 언로드

사용하지 않을 때는 반드시 언로드한다.

```bash
docker stop vllm-gemma4
nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader
```

정상 기준:

- GPU0: 한 자릿수 MiB, util 0%
- GPU1: 한 자릿수 MiB, util 0%

## 9. 문제 대응

- `/v1/health` 503: vLLM 컨테이너 상태와 포트 8000 확인.
- `/generate` 400 `no frames stored`: 먼저 frames endpoint로 프레임 push.
- `/v1/native/sessions/{id}/generate` 400 `no native window stored`: 먼저 native windows endpoint로 MP4 window push.
- Native generate audio extraction failure: stored MP4 window에 audio track이 있는지 확인.
- Native `video_url` read failure inside vLLM: Docker mount and allowed local media path configuration 확인.
- `/generate-av-fallback` returns `native_success=false`: expected degraded behavior, not a failure.
- Need native audio success evidence: current state is `native-no-go`; use Task 4, Task 5, and Task 6 evidence before changing docs or tests.
- TTFT가 계속 수 초 이상: 프레임 수, window duration, system prompt 고정 여부 확인.
- VRAM이 남아있음: `docker ps`로 컨테이너 확인 후 stop/rm.
