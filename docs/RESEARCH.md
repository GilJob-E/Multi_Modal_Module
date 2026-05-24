# 리서치 결론 — Gemma 4 멀티모달 능력과 native 오디오

작성 2026-05-24. 재정의 과정에서 이전 프로젝트의 핵심 오해를 교정한 기록.

## 한 줄 결론

**native 청각은 모델 능력 천장이 아니라 구현 버그였다.** Gemma 4 E2B/E4B는 video+audio를 native 입력받는다. 이전 "audio no-go"는 payload 포맷 오류 등이 원인일 공산이 크다.

## Gemma 4 바리언트 (2026-04-02 출시, Apache 2.0)

| 바리언트 | 파라미터(활성) | 구조 | 컨텍스트 | Text | Image | Video | **Audio** |
|---|---|---|---|---|---|---|---|
| **E2B** | 2B eff (5.1B) | Dense | 128K | ✓ | ✓ | ✓ **+오디오** | **✓** |
| **E4B** | 4B eff (8B) | Dense | 128K | ✓ | ✓ | ✓ **+오디오** | **✓** |
| **26B-A4B** | 4B 활성 / 26B | MoE(128 experts, top-8) | 256K | ✓ | ✓ | ✓ (오디오 ✗) | **✗** |
| **31B** | 31B | Dense | 256K | ✓ | ✓ | ✓ (오디오 ✗) | **✗** |

**경계: 오디오는 E2B/E4B에만 존재.** 26B-A4B·31B는 오디오 입력 거절. 또한 **E2B/E4B는 "오디오 포함 비디오"를 통째로 native 입력**받는다(`load_audio_from_video=True`); 큰 모델은 오디오 없는 비디오만.

## native 오디오 서빙 (vLLM)

- `vllm[audio]` extras 필요.
- OpenAI 호환 콘텐츠 타입 = **`audio_url`** (이전 코드의 `input_audio`는 틀림).
- 오디오 = **16kHz mono, 최대 30초, 초당 25토큰**.
- 예: `vllm serve google/gemma-4-E4B-it --max-model-len 8192 --limit-mm-per-prompt image=4,audio=1 --enable-prefix-caching`
- E4B 공식 오디오 능력 = **ASR(전사) + 음성 번역**. prosody/톤/침묵 분석은 **문서 미보장 → 실측 필요**.

## 이전 "no-go"의 진단

이전 프로젝트(베이스라인 `f80e447`의 `.sisyphus/evidence/`)는 E4B/E2B audio probe가 HTTP 400 "Invalid or unsupported audio file"이라 천장이라 결론냈다. 그러나:

1. HTTP 400은 **payload를 `{"type":"input_audio",...}`로 보낸 포맷 오류**(vLLM 규격은 `audio_url`) + `vllm[audio]` 누락 + 30초 초과 가능성이 유력.
2. 실제 `vid_0033.mp4` 테스트에서 E4B는 **HTTP 200으로 오디오를 받아 처리**하고 중간 구간 speech를 감지했다 — native 오디오가 *작동했다는 증거*. quiet-tail(약 48–50s) 한 구간을 speech로 오분류해 엄격한 proof gate에 걸렸을 뿐.

→ Phase 1 스파이크에서 `audio_url` 규격 + 30초 클립으로 재검증한다.

## 남은 실측 미지수

- E4B 단일 추론이 목표 평가 깊이에 도달하는가.
- E4B가 prosody(음량/피치/단조로움)를 묘사하는가, 전사만 하는가.
- vLLM 멀티모달 prefix 캐시가 요청 간 재사용되어 periodic prefill이 실효가 있는가.

## 출처

- [Gemma 4 발표 (Google)](https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/)
- [Welcome Gemma 4 (HF blog, 바리언트 표)](https://huggingface.co/blog/gemma4)
- [Audio understanding | Gemma docs](https://ai.google.dev/gemma/docs/capabilities/audio)
- [Gemma model overview | Google AI](https://ai.google.dev/gemma/docs/core)
- [vLLM Gemma 4 recipe](https://docs.vllm.ai/projects/recipes/en/stable/Google/Gemma4.html)
- [26B-A4B vLLM recipe](https://recipes.vllm.ai/Google/gemma-4-26B-A4B-it)
- 오디오 경계 교차확인: [litellm #25291](https://github.com/BerriAI/litellm/issues/25291)
