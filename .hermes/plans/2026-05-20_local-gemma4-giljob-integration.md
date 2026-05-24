# 최소지연 비디오-네이티브 추론 모듈 (local-infer)

**작성일:** 2026-05-20 (v2 — 범위 축소)
**내 역할:** 최소지연 실시간 비디오-네이티브 추론 파이프라인을 **독립 모듈**로 제작. 끝.
**범위 밖 (팀원 담당):** Cloudflare 제거, GilJob 통합, Gemini Live 파이프라인 접목, 프론트엔드.
**관련 기록:** `~/workspace/gje/sglang/EXPERIMENT_LOG.md` (엔진 선정 = vLLM)

---

## 0. 목표 (단일)
gemma4(video+image+audio native) 로컬 모델로, **실시간 화상 입력 → 텍스트 응답을 최소 지연으로 스트리밍**하는 추론 모듈. 깔끔한 API 경계를 가져서 누구든(=통합 담당 팀원) 갖다 쓸 수 있게 한다.

비목표: TTS, 프론트, 터널/노출, 인증 정책(최소한만), GilJob 코드.

---

## 1. 고정된 사실
- 엔진: **vLLM** (`vllm/vllm-openai:nightly`), 컨테이너 `vllm-gemma4`, 포트 8000, OpenAI 호환 API
- 모델: `google/gemma-4-31B-it` (video_url/image_url 입력 지원), TP=2 @ RTX 4090 ×2
- 베이스라인: 비디오 추론 **warm TTFT 0.30s / gen 32 TPS** (sample30.mp4, prefix cache hit)
- 입력 형태: OpenAI chat completions `messages[].content` 에 `video_url`(base64 data URL) 또는 `image_url` 다중 프레임 + text
- 한계: 모델은 텍스트만 생성. = "video/frames + text → text 스트림" 생성기.

---

## 2. 모듈 설계 (산출물)

### 위치
`~/workspace/gje/local-infer/` — vLLM과 분리된 얇은 게이트웨이/오케스트레이션 레이어.

### 왜 vLLM을 직접 안 쓰고 모듈을 두나
- **프리필 최적화**: 시스템 프롬프트(면접관 페르소나 등)를 고정 prefix로 박아 prefix-cache hit률 극대화 → TTFT 최소화. 호출자는 프롬프트 신경 안 씀.
- **실시간 프레임 관리**: 1fps 누적 프레임을 슬라이딩 윈도우로 관리(컨텍스트 4096 한정) → 호출자는 프레임만 push.
- **스트리밍 정규화**: vLLM SSE를 단순한 토큰 스트림으로 재노출 (WS or SSE).
- **레이턴시 계측 내장**: TTFT/TPS를 응답 메타로 — 원칙1 검증 상시 가능.
- **모델 교체 격리**: 나중에 엔진/모델 바뀌어도 호출자 인터페이스 불변.

### 인터페이스 (초안 — 호출자에게 노출)
- `WS /v1/stream` (1순위, 실시간 화상통화용)
  - 세션 시작 시: `{type:"init", system:"<프롬프트>", params:{...}}` → prefix 워밍
  - 프레임 push: `{type:"frame", jpeg_b64:"..."}` (1fps, 모듈이 윈도우 관리)
  - 턴 트리거: `{type:"prompt", text:"...", stream:true}` → 토큰 스트림 수신
  - 수신: `{type:"token", text}` ... `{type:"done", ttft_ms, tps, n_tokens}`
- `POST /v1/infer` (단발, 디버그/벤치용): frames[] + text → SSE 토큰 스트림 + 메타
- `GET /healthz`, `GET /metrics`

### 구현 언어
- **미정 → 사용자 확인 필요.** 후보: Python/FastAPI (vLLM 동일 생태계, 빠른 작성) vs TS/Hono (통합 팀과 동일 스택, 모듈 핸드오프 매끄러움).
- 모듈 핸드오프 대상이 GilJob(TS) 팀이면 TS가 인터페이스 합의에 유리. 추론 로직 자체는 어느 쪽이든 vLLM HTTP 호출이라 차이 작음.

---

## 3. 단계별 실행

### Phase 0 — 레이턴시 특성화 (먼저, 모듈 설계 근거 확보)
- [ ] vLLM 재기동 (`docker start vllm-gemma4`) + 베이스라인 재확인
- [ ] `infer_ttft.py` 확장 → **프레임 누적(N-frame) 벤치**:
  - 고정 시스템 프롬프트 prefix + 프레임 1·3·5·10장일 때 TTFT/TPS 곡선
  - prefix 고정 시 cache hit로 TTFT가 얼마나 떨어지는지 (warm 0.3s 재현)
  - video_url(통영상) vs image_url 다중프레임(1fps 누적) 어느 쪽이 저지연인지 비교
- [ ] vLLM 파라미터 튜닝 탐색: `--max-num-batched-tokens`, chunked prefill, `--enable-prefix-caching` 확인
- [ ] 결과 → `~/workspace/gje/local-infer/BENCH.md`

### Phase 1 — 모듈 MVP
- [ ] `~/workspace/gje/local-infer/` 스캐폴드 (+ Dockerfile, README, 인터페이스 스펙)
- [ ] `WS /v1/stream`: init(prefix 워밍) → frame push(윈도우 관리) → prompt(스트리밍 토큰)
- [ ] vLLM `/v1/chat/completions` stream=true 호출, SSE→WS 토큰 정규화
- [ ] TTFT/TPS 계측을 done 메시지에 포함
- [ ] `/healthz`, `/metrics`, 최소 토큰 인증(헤더)
- [ ] e2e: sample30.mp4를 프레임으로 분해 → 1fps push → 스트리밍 응답 + TTFT 확인

### Phase 2 — 실시간성 다지기 + 핸드오프
- [ ] 상시 연결(WS) 중 prefill 미리 워밍 → 턴 트리거 시 TTFT 추가 최소화
- [ ] 슬라이딩 윈도우/컨텍스트 4096 초과 시 프레임 eviction 정책
- [ ] 인터페이스 스펙 문서(`API.md`) — 통합 팀원이 바로 붙일 수 있게
- [ ] (선택) gemma4 audio 토큰 네이티브 STT 품질 스파이크 — 장기

---

## 4. 생길 파일
- `~/workspace/gje/local-infer/` (신규 모듈)
  - 서버 엔트리(`server.py` or `src/index.ts`), `Dockerfile`, `README.md`, `API.md`, `BENCH.md`
- `~/workspace/gje/video-test/infer_ttft.py` — N-frame 벤치로 확장 (또는 `bench_nframe.py` 신규)

## 5. 성공 기준
- 모듈 통한 스트리밍 TTFT ≈ vLLM raw TTFT (오버헤드 최소, 목표 < 0.5s warm)
- 1fps 프레임 push + 상시 WS에서 턴 트리거 시 첫 토큰까지 지연 최소
- 인터페이스가 깔끔해 통합 팀원이 모듈만 보고 연결 가능 (vLLM 내부 비노출)
- 모델/엔진 교체해도 인터페이스 불변

## 6. 리스크 / 오픈 퀘스천
- video_url(전체영상 재인코딩) vs 누적 프레임 image_url — 실시간엔 후자가 유리할 것이나 벤치로 확정.
- 컨텍스트 4096 + 누적 프레임 → 토큰 압박. 프레임 해상도/장수 트레이드오프 측정 필요.
- 4090×2 단일세션 전제. 다중 동시 세션은 범위 밖(필요 시 별도).
- **구현 언어 결정 필요** (Python vs TS).

## 7. 다음 즉시 액션
1. **Phase 0** 시작: vLLM 재기동 → N-frame 프리필/스트리밍 TTFT 벤치 → BENCH.md
2. 구현 언어(Python/TS) 사용자 확인 후 Phase 1.
