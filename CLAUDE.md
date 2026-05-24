# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 지금 상태 (중요)

이 워크스페이스는 2026-05-24에 **재정의 후 깨끗하게 재시작**되었다. 이전 `local-infer` 구현 전체(코드·테스트·문서·증거)는 git 베이스라인 커밋 `f80e447`에 보존돼 있다. 작업트리에는 프레임 문서와 fixture만 있고 코드는 아직 없다. 재사용 가능한 이전 코드는 `docs/DECISIONS.md`의 표를 보고 `git checkout f80e447 -- <path>`로 의도적으로 되살린다.

문서는 한국어. 편집 시 같은 언어를 유지한다.

## 무엇을 만드는가

로컬 LLM(vLLM + Gemma 4)으로 면접 답변을 **언어·청각·시각 종합 평가**해 풍부한 피드백을 **턴 단위로 즉시** 내는 추론 모듈. 핵심 방법론은 **periodic prefill**(발화 중 선행 prefill → 턴 종료 시 즉시 generate). 자세한 목적·기준은 `README.md`.

## 먼저 읽을 것

- `README.md` — 프로젝트 목적·성공 기준·디렉터리
- `docs/PLAN.md` — 실행 계획 (Phase 1 검증 스파이크부터)
- `docs/RESEARCH.md` — Gemma 4 바리언트 능력, native 오디오 핵심 발견과 출처
- `docs/DECISIONS.md` — 엔진/모델/벤치 결정, 재사용 코드 포인터

## 반드시 기억할 사실 (재발 방지)

- **오디오는 Gemma 4 E2B/E4B에만 있다.** 31B·26B-A4B는 오디오 입력 불가. 들으려면 E2B/E4B.
- **이전의 audio "no-go"는 모델 천장이 아니라 payload 버그였다.** vLLM Gemma 4 오디오 콘텐츠 타입은 **`audio_url`**(이전 `input_audio`는 틀림). `vllm[audio]` extras 필요. 오디오는 16kHz mono, 최대 30초. 이 오해를 다시 "능력 한계"로 결론내지 말 것.
- **저수준 feature extraction으로 빠지지 말 것.** 목표는 모델이 직접 이해하는 native 평가다.

## GPU 위생 규칙 (필수)

모델 미사용 시 컨테이너를 stop하고 VRAM 해제를 확인한다.

```bash
docker stop <vllm-container>
nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader
```

## fixture

- `vid_0033.mp4` — 실제 면접 영상. Phase 1 스파이크 fixture. gitignore라 git에 없으니 **삭제 금지**(소실 시 복구 불가). quiet tail이 약 48–50s에 있음.
