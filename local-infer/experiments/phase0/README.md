# Phase 0 벤치 — Gemma4/vLLM 비디오 네이티브 저지연 입력 방식

**일시:** 2026-05-20  
**목적:** 실시간 화상통화용 로컬 Gemma4 추론 모듈의 입력 인터페이스를 결정한다.  
**엔진:** `vllm/vllm-openai:nightly`, `google/gemma-4-31B-it`, TP=2, fp8, max_model_len=4096  
**하드웨어:** RTX 4090 × 2 (24GB × 2)  

## 결론

**모듈 입력 방식은 A안: 누적 프레임(`image_url` 다중, 1fps)으로 확정.**

이유:
- 실시간 화상통화의 자연스러운 입력 단위가 “프레임 push”다.
- 같은 프레임/고정 프롬프트 재요청 시 vLLM prefix cache가 잘 먹어서 warm TTFT가 **0.16~0.24s**까지 내려간다.
- `video_url` 전체 영상 방식은 cold TTFT가 **~8s**로 너무 크고, 매 턴 영상 클립을 재인코딩/전송하는 구조라 실시간 모듈 인터페이스로 부적합하다.
- 1~5프레임 누적은 cold TTFT도 **~2.0s** 수준이라, 실제 대화 중에는 “프레임 prefill/캐시 유지 + 짧은 질문 생성” 방식으로 latency budget을 맞출 수 있다.

## 실험 A — 누적 프레임 `image_url[]`

스크립트: `~/workspace/gje/video-test/bench_nframe.py`  
프레임: `~/workspace/gje/video-test/frames/f001.jpg` … `f030.jpg`  
프롬프트: 고정 system prompt + “표정/자세 묘사 + 후속 질문 1개”  

- N=1
  - raw: 0.7KB
  - cold TTFT: 2.768s
  - warm TTFT: 0.191s
  - TPS: cold 27.1 / warm 34.7 chunks/s
- N=3
  - raw: 7.2KB
  - cold TTFT: 2.012s
  - warm TTFT: 0.169s
  - TPS: cold 34.2 / warm 34.3 chunks/s
- N=5
  - raw: 19.0KB
  - cold TTFT: 2.005s
  - warm TTFT: 0.243s
  - TPS: cold 34.2 / warm 34.2 chunks/s
- N=10
  - raw: 64.9KB
  - cold TTFT: 4.425s
  - warm TTFT: 0.161s
  - TPS: cold 33.6 / warm 33.8 chunks/s

### 관찰

- 1~5프레임까지 cold TTFT는 약 2초대. 10프레임부터 cold prefill 비용이 커진다.
- warm TTFT는 N=10까지도 0.16~0.24초로 매우 낮다.
- 즉 “항상 전체 프레임을 새로 이해시키는 구조”가 아니라, 세션별로 프레임 prefix를 캐시에 태우는 구조가 중요하다.

## 실험 B — 전체 영상 `video_url`

스크립트: `~/workspace/gje/video-test/infer_ttft.py sample30.mp4`  
입력: 30초 MP4 전체를 base64 `video_url`로 전송  
프롬프트: “영상에서 일어나는 일을 시간 순서대로 설명”  

- run1/cold
  - TTFT: 7.976s
  - total: 15.931s
  - output chunks: 257
  - TPS: 32.31 chunks/s
- run2/warm
  - TTFT: 0.233s
  - total: 8.203s
  - output chunks: 257
  - TPS: 32.25 chunks/s

### 관찰

- warm TTFT는 낮지만, cold TTFT가 너무 크고 30초 전체 영상 전송/인코딩 단위가 실시간 스트리밍 모듈에 맞지 않는다.
- 출력 길이가 길어 total latency도 크다. 실시간 면접 모듈은 `max_tokens`를 낮게 잡고 짧은 후속질문/분석을 반환해야 한다.

## 모듈 설계 결정

### 입력

세션 기반 프레임 push:

```json
{
  "session_id": "...",
  "timestamp_ms": 12345,
  "frame_jpeg_base64": "...",
  "audio_state": "optional_transcript_or_vad_state"
}
```

### 추론 트리거

- 기본: 1fps로 frame buffer에 축적.
- 턴 종료/VAD 이벤트/사용자 발화 텍스트 도착 시 최근 N프레임을 `image_url[]`로 묶어 vLLM에 요청.
- 초기값: `N=3~5`.
- 긴 구간은 모든 프레임을 누적하지 않고 keyframe/summary로 압축한다.

### 출력

SSE 또는 WebSocket token stream:

```json
{"type":"token","text":"...","latency":{"ttft_ms":169}}
{"type":"final","text":"...","usage":{...},"frames_used":5}
```

## FastAPI MVP smoke test

`~/workspace/gje/local-infer/`에 FastAPI 모듈을 생성한 뒤 실제 vLLM에 붙여 smoke test 수행.

- 최초 `/generate` after frame push
  - frames_used: 5
  - TTFT: 3892ms
  - total: 4956ms
  - 해석: 새 multimodal prefill 비용 포함.
- 동일 세션/동일 프레임 재요청
  - run1 TTFT: 149ms, total 1.208s
  - run2 TTFT: 162ms, total 1.216s
  - 해석: prefix cache hit. 모듈 목표인 warm-path 저지연 가능성 확인.

## 구현된 다음 단계

1. `~/workspace/gje/local-infer/` FastAPI 모듈 생성 완료.
2. `/v1/sessions/{id}/frames` — 프레임 수집 완료.
3. `/v1/sessions/{id}/generate` — 최근 N프레임 + 텍스트로 vLLM streaming 호출 완료.
4. `/v1/health` — vLLM readiness 요약 완료.
5. 단위 테스트 6개 통과.

## GPU 상태

실험 종료 후 vLLM 컨테이너 stop 및 `nvidia-smi` 확인 완료: GPU0 9MiB / GPU1 1MiB, util 0%.

