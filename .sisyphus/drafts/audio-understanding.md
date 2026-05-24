# Draft: Audio Understanding

## Requirements (confirmed)
- Target direction: "video+audio native 실시간 면접 모델", "오디오까지 분석하는 멀티모달 면접관", "비디오 스트림을 네이티브로 이해하는 시스템".
- Practical product target: given an instruction like "내가 하늘을 보면서 아~ 라고 목소리를 내면 반응해", during live conversation the system should detect the combined visual cue (looking at the sky) plus vocal cue ("아~") and respond within about 2 seconds.
- Current request: "오디오이해되는 상태 만들어와. 다른 모델이든 엔진이든 아니면 작은 변경이든 알아서 잘, 현업 AI ops 전문가 답게 해와".
- Current finding from live check: MP4 files contain AAC audio, but current vLLM `video_url` inference returned `NO_AUDIO_DETECTED` / `오디오를 확인할 수 없음` for audio-focused prompts.
- First success criterion: Native 우선 — prioritize a single video+audio native model/engine path over a composed ASR + vision fallback.
- Operating boundary: 로컬 GPU만 — working path must run on the local GPU/server environment; cloud/API models may not be the success path.

## Technical Decisions
- Treat current `local-infer` JPEG frame path as interim MVP, not final framing.
- Plan must produce a working audio-understanding path, with ranked routes: smallest change first, fallback engine/model paths if needed.
- Verification must prove audio understanding via controlled ablation: audio-present vs audio-removed same video, plus audio-only/black-video test.
- Route ranking should privilege final-product alignment even if a composed fallback is listed as contingency.
- Candidate models/engines must fit or be made to fit the local GPU constraints before being accepted as the primary route.

## Research Findings
- Repo exploration: current production `local-infer` has no audio ingestion, no `audio_url`/`input_audio`, no STT/VAD dependencies; production path is `image_url[]` frames + text.
- Oracle: most likely current failure is not MP4 upload but audio track not entering model tokens; must prove audio-token ingestion through atomic probes before integration.
- Librarian: current `google/gemma-4-31B-it` stack is not the native audio path; Gemma4 E2B/E4B are the same-family audio-capable candidates; Qwen2.5-Omni is stronger unified AV candidate but higher serving risk; ASR sidecar is fallback only.
- Metis: plan must keep Native-first/local-only hard constraints, separate native AV path from fallback ASR, preserve current 31B vision baseline, and include happy/no-audio/beep/Korean/audio-video-sync probes.

## Open Questions
- Is using a composed pipeline (ASR/audio emotion/paralinguistics + Gemma4 vision) acceptable as an interim operational state, or must the first working state be a single native audio-video model path?
- Hardware/VRAM budget details beyond existing repo assumption of RTX 4090 × 2, if that assumption is no longer current.

## Defaults Applied
- Hardware assumption: use documented RTX 4090 × 2 local environment unless executor observes a different `nvidia-smi` result.
- Primary candidate order: Gemma4 E4B → Gemma4 E2B → Qwen2.5-Omni native probe → local ASR fallback only after native no-go evidence.
- Test policy: tests-after with isolated probe scripts first, then app integration tests after native audio is proven.

## Scope Boundaries
- INCLUDE: audio input support investigation, model/engine alternatives, empirical verification plan, API/interface impact, rollback/fallback strategy.
- EXCLUDE: implementing changes in this planning session, production deployment beyond local AI Ops validation unless explicitly requested.
