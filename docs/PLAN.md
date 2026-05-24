# 재정의: 실시간 턴 단위 native 멀티모달 면접 평가 모듈

## Context (왜 이 작업을 하는가)

`local-infer`는 원래 "실시간 화상 입력 → 텍스트 응답을 최소지연 스트리밍하는 로컬 추론 모듈"로 시작했지만, 진행 중 **native audio "no-go" 검증과 그에 딸린 방어적 disclaimer 문서·3중 경로(native override / degraded fallback)** 로 흐름이 지저분해졌다. 사용자는 결과물이 마음에 안 들어 "핵심만 남기고 재시작"하기로 했다.

재정의된 목적은 명확하다: **로컬 LLM으로 nativeness와 latency를 동시에 최대화**해서, 면접 답변을 **언어(verbal)·청각(vocal)·시각(visual) 종합**으로 평가하는 풍부한 피드백을 **턴(답변) 단위로 즉시** 생성한다. 핵심 방법론은 **periodic prefill**(발화 중 선행 prefill → 턴 종료 시 즉시 generate).

리서치가 이전의 핵심 오해를 교정했다:
- **native 청각은 천장이 아니라 구현 버그였다.** Gemma 4 **E2B/E4B는 video+audio를 native 입력**받는다(ASR/번역 공식 지원). 이전 HTTP 400 "Invalid or unsupported audio file"는 ① payload를 `input_audio`로 보낸 포맷 오류(vLLM 규격은 `audio_url`) ② `vllm[audio]` extras 누락 ③ 30초 초과 가능성 때문일 공산이 크다.
- **31B·26B-A4B는 오디오 입력이 없다**(text/image/video만). 즉 오디오를 들으려면 E2B/E4B를 써야 한다 → 모델 트레이드오프 발생.
- E4B 오디오 공식 능력은 ASR/번역까지이고, prosody(음량/피치) 묘사는 **미보장 → 실측 필요**.

출처: [Gemma 4 blog](https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/), [Gemma audio docs](https://ai.google.dev/gemma/docs/capabilities/audio), [vLLM Gemma4 recipe](https://docs.vllm.ai/projects/recipes/en/stable/Google/Gemma4.html).

안전장치: 재시작 전 현재 전체 상태를 git 베이스라인으로 커밋 완료(commit `f80e447`, 203파일). 무엇을 지워도 복구 가능.

## 성공 기준 (재확인)

1. 출력 품질: 사용자가 제시한 예시 수준의 풍부한 verbal/vocal/visual 종합 평가.
2. 실시간성: 턴 종료(VAD/end-of-turn) 시 첫 토큰 지연 최소(목표 warm TTFT < 0.5s), periodic prefill로 달성.
3. nativeness: 청각·시각을 가능한 한 모델이 직접 이해(저수준 feature dump 지양).
4. 깔끔한 단일 인터페이스(vLLM 비노출), 모델/엔진 교체 시 인터페이스 불변.

---

## Phase 1 — 검증 스파이크 (먼저, 아키텍처 확정용)

목적: 문서로 못 정하는 경험적 미지수를 싸게 걷어내고 아키텍처 (1)단일 E4B vs (2)2-스테이지를 확정.

### 1.1 E4B 오디오 서빙 기동
- 새 launch config `sglang/launch-configs/vllm_e4b_audio.sh` 작성(31B용 `vllm_baseline.sh`는 보존).
- 핵심: `vllm[audio]` extras 포함 이미지/설치, E4B는 작아서 단일 GPU(TP 불필요).
  ```bash
  vllm serve google/gemma-4-E4B-it \
    --max-model-len 8192 \
    --limit-mm-per-prompt image=4,audio=1 \
    --enable-prefix-caching
  ```
- `/v1/models` ready 확인. 종료 시 GPU 언로드 규칙 준수.

### 1.2 payload 교정
- `native_payloads.py`의 `{"type":"input_audio",...}` → **`{"type":"audio_url","audio_url":{"url": "<data: 또는 file:// URL>"}}`** 로 교정.
- 오디오는 **16kHz mono WAV, ≤30초**. `native_audio.py`가 이미 mono 16kHz 추출 → 30초 클리핑만 추가.

### 1.3 프로브 (기존 `tools/probe_gemma4_real_video.py` 적응, 새 `tools/spike_e4b_native_av.py`)
`vid_0033.mp4`에서 **≤30초 윈도우**를 잘라 측정:
1. **Native AV 동작 + 전송 방식**: (a) `video_url` 단독으로 E4B가 영상의 오디오까지 듣는가, (b) `video_url` + 별도 `audio_url` 조합 — 둘 중 무엇이 HTTP 200 + 보고/들은 내용 일치하는지 확인.
2. **품질 루브릭**: 전체 verbal/vocal/visual 평가 프롬프트 → 출력이 예시 수준인가 채점(구조적 verbal 평가 / vocal 전달력 / visual 단서 각 항목 유무·깊이).
3. **prosody 프로브**: "음량 변화·말 속도·pause·억양 단조로움을 짚어줘" 류 프롬프트 → 실제 묘사하는가, 단순 전사만 하는가.
4. **지연**: E4B native AV generate의 TTFT/total 측정.
- 증거를 `.sisyphus/evidence/spike-e4b-native-av.json`에 기록.

### 1.4 결정 규칙 (GO/NO-GO → 아키텍처)
- E4B native AV 동작 **AND** 품질·prosody 충분 → **(1) 단일 E4B**.
- E4B native AV 동작하나 추론 얕음 **OR** prosody 약함 → **(2) 2-스테이지**: E4B가 native 청각(전사+가능한 vocal)·시각 추출 → **26B-A4B**(4B 활성, 빠름) 또는 **31B**가 종합 추론.
- VRAM: E4B(~8GB) 단독 스파이크 먼저. (2) 선택 시 E4B + 대형모델 2×4090(48GB) 동시 적재 가능성/순차 적재를 별도 검증.

---

## Phase 2 — 군더더기 절단 & 깨끗한 토대

git 베이스라인(`f80e447`)에 복구 태그 부여 후:
- **유지(재사용 인프라)**: `vllm_client.py`, `vllm_stream.py`, `frame_store.py`, `native_media_store.py`, `native_audio.py`, `experiments/phase0`, `video-test/`, `sglang/EXPERIMENT_LOG.md`.
- **제거(cruft)**: `audio_analysis.py`, degraded fallback 엔드포인트(`/audio`, `/generate-av-fallback`), "user override native" disclaimer 레이어, 그리고 README/INFERENCE_PIPELINE/docs/DECISIONS의 "not native success / fallback is not proof" 방어 문서 더미. (히스토리는 git 베이스라인에 보존되므로 본문에서 삭제.)
- **교정**: `native_payloads.py`를 `audio_url` 규격으로 확정.
- **문서 재작성**: 3중 경로 미로를 버리고 단일 일관 아키텍처로 README/CLAUDE.md/ARCHITECTURE 재서술.

## Phase 3 — 턴 단위 native 파이프라인 + periodic prefill

- **세션 기반 엔드포인트**: 턴 진행 중 AV 윈도우 push → end-of-turn 트리거 → 평가 SSE 스트리밍.
- **periodic prefill 기제**: `--enable-prefix-caching` 켠 상태에서, 턴 중 고정 system prompt prefix + 누적 AV 윈도우를 주기적으로 선전송해 vLLM이 prefix를 캐시 → 턴 종료 시 warm prefix 재사용으로 TTFT 최소화. **(멀티모달 prefix 캐시가 요청 간 재사용되는지는 측정 대상; Phase0가 image_url 경로 warm 0.16–0.24s는 입증.)**
- **30초 오디오 캡 ↔ 긴 답변**: rolling window 전략으로 화해(최근 윈도우 기준 평가 + 누적 요약).
- **재사용 우선**: AV 윈도우는 `native_media_store`, 스트리밍은 `vllm_client`/`vllm_stream`. 신규는 prefill 워밍 루프 + 턴 트리거 로직만.
- 아키텍처 분기: (1) 단일 E4B 1콜 / (2) E4B 추출 → fusion 모델 2단.

## Phase 4 — 검증

- 스파이크 루브릭을 완성 파이프라인에 재적용(품질 회귀 방지).
- **periodic prefill 효과 측정**: 같은 턴을 prefill 워밍 on/off로 end-of-turn TTFT 비교 → 방법론이 실제로 지연을 줄이는지 정량 입증.
- `PYTHONPATH=src uv run --with pytest --with httpx pytest tests -q` 전체 통과(군더더기 제거 후 테스트도 정리).

## Project-manager 스캐폴딩 (병행)

- 프로젝트 프레임 문서(목적·기준·디렉터리)와 CLAUDE.md를 교정된 내용으로 갱신.
- 메모리 저장: "E4B native audio는 viable; 이전 no-go는 `input_audio` payload 버그·`vllm[audio]` 누락·30초 캡 때문" — project 메모리로 기록(재발 방지).

## 핵심 변경 파일 요약

| 파일 | 작업 |
|---|---|
| `sglang/launch-configs/vllm_e4b_audio.sh` | 신규 — E4B+audio 서빙 |
| `tools/spike_e4b_native_av.py` | 신규 — Phase1 스파이크(기존 probe 적응) |
| `src/local_infer/native_payloads.py` | 교정 — `input_audio`→`audio_url` |
| `src/local_infer/native_audio.py` | 30초 클리핑 추가 |
| `src/local_infer/app.py` | fallback 엔드포인트 제거 + 턴/prefill 엔드포인트 |
| `src/local_infer/audio_analysis.py` 등 | 제거 |
| README / INFERENCE_PIPELINE / docs / CLAUDE.md | 재작성 |

## 미해결·실측 의존 항목
- E4B 단일 추론이 목표 평가 깊이에 도달하는가 (Phase1이 판정).
- E4B가 prosody를 묘사하는가, 아니면 전사만 하는가 (Phase1).
- vLLM 멀티모달 prefix 캐시가 요청 간 재사용되어 periodic prefill이 실효가 있는가 (Phase3/4 측정).
- 아키텍처 (2) 선택 시 E4B + 대형모델 2×4090 동시 적재 가능 여부.
