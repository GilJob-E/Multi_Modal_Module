# Thinking Machines — Interaction Models 조사 노트

원문: https://thinkingmachines.ai/blog/interaction-models/  
일시: 2026-05-20  
목적: GilJob local-infer의 실시간 video-native 추론 파이프라인 설계에 적용 가능한 개념 정리.

## 핵심 주장

Thinking Machines 글의 핵심은 기존 LLM 인터페이스가 **turn-based**라서 실시간 협업에 구조적으로 불리하다는 것이다.

기존 turn-based 모델:

```text
user input complete → model output complete → next user input
```

문제:
- 사용자가 말하거나 행동하는 동안 모델은 기다린다.
- 모델이 생성하는 동안 새 입력 인지가 멈춘다.
- interruption, overlap, silence, visual cue 같은 상호작용 신호가 모델 컨텍스트에 자연스럽게 들어가지 않는다.

제안하는 interaction model:

```text
continuous audio/video/text streams
→ time-aligned micro-turns
→ model perceives/responds/acts in real time
```

## 중요한 개념

### 1. Time-aligned micro-turns

- 200ms 단위 입력/출력 chunk를 interleave한다.
- 완성된 user turn을 기다리지 않는다.
- silence, interruption, overlap, backchannel이 모델 컨텍스트 일부가 된다.

개념적 형태:

```text
input_0 output_0 input_1 output_1 input_2 output_2 ...
```

### 2. Interaction model + background model split

실시간 모델은 계속 사용자와 상호작용하고, 긴 reasoning/tool 작업은 background model에 위임한다.

```text
interaction model: presence, turn-taking, visual/audio cue, immediate response
background model: deeper reasoning, tools, long-horizon work
```

GilJob에 대응하면:
- local-infer 실시간 path: 짧은 관찰/후속질문/시각 cue 반응
- background path: 답변 품질 평가, RAG, 사후 분석, 리포트 생성

### 3. Streaming sessions

글에서 가장 직접적으로 중요한 구현 포인트:

> 200ms chunks require frequent prefills and decodes of small sizes. Existing LLM inference libraries are not optimized for frequent small prefills. They implemented streaming sessions: the client sends each 200ms chunk separately, while the inference server appends these chunks into a persistent sequence in GPU memory.

즉 저지연 실시간 모델의 핵심은 매번 새 요청으로 전체 prefix를 다시 만들지 않는 것이다.

```text
bad: each request rebuilds full multimodal context
better: persistent session in GPU memory, append small chunks
```

### 4. Visual proactivity

오디오 VAD만으로 turn boundary를 잡는 시스템은 visual event에 자발적으로 반응하기 어렵다.

예:
- pushup count
- 어떤 행동이 시작/종료되는 순간 말하기
- 질문의 답이 영상 속 특정 순간에 나타날 때 그때 답하기

GilJob 면접 도메인 대응:
- 사용자가 시선을 회피하기 시작함
- 답변 중 자세가 무너짐
- 긴 침묵/불안정한 표정 변화 발생
- 면접관이 꼭 사용자 음성 종료만 기다리지 않고 visual cue 기반으로 backchannel 가능

## GilJob local-infer에 주는 시사점

### A. 현재 MVP의 한계

현재 local-infer는:

```text
frame push → in-memory frame buffer → generate 시 recent N frames를 vLLM에 전송
```

이는 turn-based OpenAI-compatible API 위의 thin gateway다. 진짜 interaction model은 아니다.

한계:
- frame push만으로 vLLM GPU state가 append되지 않는다.
- `/generate` 호출 전까지 vLLM은 프레임을 보지 않는다.
- end-of-turn 최초 generate는 기본적으로 request-cold에 가깝다.

### B. 다음 목표는 “persistent streaming session 흉내내기”

vLLM OpenAI API가 Thinking Machines식 micro-turn GPU append를 직접 제공하지 않는다면, local-infer는 다음 단계 실험을 해야 한다.

1. End-of-turn cold baseline
2. Periodic prefill request
3. Append-only prefix request
4. Sliding-window request
5. Session summary/keyframe compression

목표는 질문:

> vLLM/Gemma4에서 현재 API로 어느 정도까지 streaming session 비슷한 효과를 낼 수 있는가?

에 답하는 것이다.

### C. 200ms는 현재 Gemma4/vLLM에는 과격한 목표

Thinking Machines는 interaction-native model을 scratch training했고 inference stack도 streaming sessions에 맞췄다. 현재 우리는 범용 Gemma4 + vLLM OpenAI API를 사용한다.

따라서 200ms micro-turn을 그대로 복제하는 것보다 현실적인 단계는:

- 1fps frame sampling 유지
- end-of-turn generate latency 최소화
- visual cue background monitoring 실험
- 가능하면 500ms~1s 단위 prefill 실험

### D. 실시간 path와 background path 분리

글의 interaction/background model split은 GilJob에도 유효하다.

- 실시간 path: 짧은 반응, 후속 질문, visual cue monitoring
- background path: 답변 평가, RAG, 종합 피드백, 리포트

local-infer API도 장기적으로 두 계층으로 나누는 것이 적절하다.

## 적용 우선순위

1. `generate`만 최적화하지 말고, `session` 개념을 강화한다.
2. `/frames`가 단순 저장으로 끝나지 않고, prefill/monitoring 실험을 트리거할 수 있게 확장한다.
3. 다음 벤치는 cold/warm 재요청이 아니라 다음 4축으로 설계한다.
   - end-of-turn cold
   - periodic prefill
   - append-only prefix
   - sliding window
4. 결과가 좋으면 API에 `/v1/sessions/{id}/prefill` 또는 background prefill worker를 추가한다.
5. 결과가 나쁘면 현재 MVP처럼 recent N image frames + short output을 기본 경로로 유지하고, visual proactivity는 별도 lightweight model/heuristic으로 분리한다.

## 결론

Thinking Machines 글은 우리 프로젝트에 대해 다음 교훈을 준다.

- 단순 `video_url`/`image_url[]` 선택보다 더 중요한 문제는 **turn-based 요청 구조를 얼마나 벗어날 수 있느냐**다.
- 진짜 저지연 실시간 시스템은 모델이 사용자가 말하는 동안 계속 보고/듣고 있어야 한다.
- 하지만 현재 Gemma4/vLLM 조합은 interaction-native가 아니므로, 우선은 API-level에서 persistent session/prefill 효과를 실험해야 한다.
- local-infer의 다음 단계는 “프레임 버퍼 서버”가 아니라 “streaming session을 흉내내는 저지연 orchestrator”가 되어야 한다.
