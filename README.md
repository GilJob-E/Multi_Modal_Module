# gje — 실시간 native 멀티모달 면접 평가 모듈

로컬 LLM(vLLM + Gemma 4)으로 면접 답변을 **언어(verbal)·청각(vocal)·시각(visual) 종합**으로 평가하는 풍부한 피드백을, **턴(답변) 단위로 즉시** 생성하는 독립 추론 모듈.

> 이 워크스페이스는 2026-05-24 재정의 후 깨끗하게 재시작되었다. 이전 구현 전체는 git 베이스라인 커밋 `f80e447`에 보존돼 있어 언제든 복구 가능하다.

## 목적

로컬 LLM으로 **nativeness와 latency를 동시에 최대화**한다. 모델이 시각·청각을 직접 이해해(저수준 feature dump 지양) 아래 수준의 평가를 실시간으로 낸다:

- **언어적(Verbal)**: 답변 내용의 논리·구조·구체성·키워드
- **청각적(Vocal)**: 톤·억양 단조로움·발음·말 속도·pause·자신감
- **시각적(Visual)**: 시선 처리·표정·제스처·화면 구도·조명

**처리 전략 (모달리티별, 2026-05-24 실측으로 재정의).** 한때 간판으로 삼았던 *periodic prefill*은 ≤30s·E4B에서 **불필요**함이 드러났다 — 오디오 인코더가 클립을 소수 토큰으로 압축해 **cold prefill이 이미 싸기** 때문(신선 콘텐츠 30s end-to-end <0.2s). 대신 모달리티 특성에 맞춘다:

- **청각/언어 (audio)**: ≤30s 윈도우를 모델에 통째로 준다. latency는 모델 속성으로 충족되고, 유일한 비용은 부팅 1회성 워밍업(기동 시 더미 요청으로 선warm).
- **시각 (visual)**: 다중 프레임을 한 프롬프트에 넣으면 시간 binding이 깨지므로(환각), **프레임별 단일 분석 + 타임라인 집계**로 푼다. 프레임은 턴 내내 도착하니 발화 중 분산 처리(프레임당 ~60ms, 병렬) → 턴 종료엔 집계만. **incremental 처리가 실효 있는 모달리티는 비전이다.**

비목표: TTS, 프론트엔드, 터널/노출, GilJob 통합 코드, Gemini Live.

## 성공 기준

1. 출력 품질이 위 verbal/vocal/visual 종합 평가 수준에 도달.
2. 턴 종료 시 first-token < 0.5s. 오디오는 cold로 이미 충족(30s ~0.12s), 시각은 프레임별 처리를 발화 중 분산해 충족.
3. 청각·시각을 가능한 한 모델이 native로 이해.
4. vLLM을 숨긴 깔끔한 단일 인터페이스, 모델/엔진 교체에도 인터페이스 불변.

## 현재 상태

**아키텍처 (1) 단일 E4B native AV 확정(Phase 1)** + **처리 전략 실측 확정(cold kill-test +
시각 시간축 스파이크, 2026-05-24).**

- **청각/언어**: `audio_url`(data URL) + `vllm[audio]` 파생 이미지로 E4B가 native AV를
  HTTP 200 처리, prosody 묘사·평가 깊이 충분. **cold prefill이 싸다** — 신선 콘텐츠
  30s end-to-end <0.2s, latency 목표를 periodic prefill 없이 충족(증거
  `spike-cold-prefill.json`). 최초 "31.5배"는 best-case 오측이라 철회됨.
- **시각**: 단일 프레임 카운팅은 정확하나, **다중 프레임을 한 프롬프트에 넣으면 시간
  binding이 깨진다**(환각). → **프레임별+집계** 아키텍처가 실제 제스처를 추적하며
  프레임당 ~60ms·병렬로 싸다(증거 `spike-visual-fingers.json`,
  `spike-visual-temporal-v2.json`). 잔여 천장 = 인접값 카운팅 fidelity(질적 평가엔 허용).
- Phase 2 폐지·흡수, Phase 3 부분완료(인터페이스·품질·nativeness), Phase 4 백지화.

**다음**: 시각 시간축 트랙(프레임별+집계, smart 집계기)을 `native_eval`에 통합하고 audio
평가와 합치는 턴 파이프라인 재설계. 상세 `docs/PLAN.md`.

## 디렉터리

```text
gje/
├── README.md          # 이 문서 (프로젝트 프레임)
├── CLAUDE.md          # Claude Code용 작업 가이드
├── docs/
│   ├── PLAN.md        # 재정의 실행 계획 (Phase 1~4)
│   ├── RESEARCH.md    # Gemma 4 바리언트·native 오디오 리서치 결론 + 출처
│   └── DECISIONS.md   # 엔진/모델/벤치 결정과 근거, 재사용 코드 포인터
├── vid_0033.mp4       # 실제 면접 fixture (gitignore, 디스크에만 존재)
└── 졸업작품2_중간보고_3분반_1조 (2).docx   # 중간보고서 (레퍼런스)
```

## 외부 의존

- vLLM 컨테이너(OpenAI 호환 API, 포트 8000), 모델 캐시 `~/hf_cache/`
- 하드웨어: RTX 4090 × 2 (24GB × 2)
- **GPU 위생 규칙**: 모델 미사용 시 컨테이너 stop + VRAM 해제 확인
  ```bash
  docker stop <vllm-container>
  nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader
  ```
