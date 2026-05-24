# gje — 실시간 native 멀티모달 면접 평가 모듈

로컬 LLM(vLLM + Gemma 4)으로 면접 답변을 **언어(verbal)·청각(vocal)·시각(visual) 종합**으로 평가하는 풍부한 피드백을, **턴(답변) 단위로 즉시** 생성하는 독립 추론 모듈.

> 이 워크스페이스는 2026-05-24 재정의 후 깨끗하게 재시작되었다. 이전 구현 전체는 git 베이스라인 커밋 `f80e447`에 보존돼 있어 언제든 복구 가능하다.

## 목적

로컬 LLM으로 **nativeness와 latency를 동시에 최대화**한다. 모델이 시각·청각을 직접 이해해(저수준 feature dump 지양) 아래 수준의 평가를 실시간으로 낸다:

- **언어적(Verbal)**: 답변 내용의 논리·구조·구체성·키워드
- **청각적(Vocal)**: 톤·억양 단조로움·발음·말 속도·pause·자신감
- **시각적(Visual)**: 시선 처리·표정·제스처·화면 구도·조명

핵심 방법론은 **periodic prefill**: 발화 중 들어오는 프레임/오디오를 미리 prefill해, 턴 종료(VAD/end-of-turn) 시점에 첫 토큰 지연을 최소화한다.

비목표: TTS, 프론트엔드, 터널/노출, GilJob 통합 코드, Gemini Live.

## 성공 기준

1. 출력 품질이 위 verbal/vocal/visual 종합 평가 수준에 도달.
2. 턴 종료 시 warm TTFT < 0.5s (periodic prefill로 달성).
3. 청각·시각을 가능한 한 모델이 native로 이해.
4. vLLM을 숨긴 깔끔한 단일 인터페이스, 모델/엔진 교체에도 인터페이스 불변.

## 현재 상태

**Phase 1 검증 스파이크 완료(2026-05-24) → 아키텍처 (1) 단일 E4B native AV 확정.**
`audio_url`(data URL) 규격 + `vllm[audio]` 파생 이미지로 E4B가 native AV를 HTTP 200
처리, prosody 묘사·평가 깊이·prefix 캐시 재사용 모두 실측 통과(증거
`.sisyphus/evidence/spike-e4b-native-av.json`). 이전 audio "no-go"는 모델 천장이
아니라 payload 버그였음 확인. 검증된 전송 = 샘플 프레임(`image_url`) + `audio_url`.

**Phase 3**(턴 파이프라인 + periodic prefill)에서 평가자 인터페이스·품질·nativeness는
구현·확인됐으나, **간판 방법론인 periodic prefill의 latency 실효는 미입증이다.** 최초
"31.5배 단축"은 하니스가 최종 오디오를 미리 쥔 best-case 측정이었고(정정됨), 라이브에선
최종 오디오가 턴 종료 시점에야 확정돼 미리 데울 수 없다. 다음 단계는 이 갭을 cold
조건에서 검증하는 **cold kill-test 스파이크**(`docs/PLAN.md` "## 남은 갭"). Phase 2는
폐지·흡수, Phase 4는 백지화됨.

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
