# Task 2 Native Model and Engine Decision

## Decision

Attempt native local audio understanding in this fixed order:

1. `gemma4-e4b` with `google/gemma-4-E4B-it` on local vLLM.
2. `gemma4-e2b` with `google/gemma-4-E2B-it` on local vLLM if E4B records no-go evidence.
3. `qwen2.5-omni` with a local Qwen2.5-Omni route only if both Gemma candidates fail.
4. `local-asr-contingency` only as degraded fallback after every native route has no-go evidence.

The product target remains cross-modal: detect a combined visual cue plus vocal cue, for example looking upward while vocalizing "아~", and respond within about 2 seconds after the event is observable. Native success requires explicit audio-token ingestion plus visual context, not transcript fusion.

## Why Current 31B Is Excluded

The current `google/gemma-4-31B-it` route is excluded from native audio success. Local evidence in `.sisyphus/evidence/task-1-31b-negative.json` records that the vLLM `video_url` AAC MP4 path did not understand audio, with results such as `NO_AUDIO_DETECTED` and `오디오를 확인할 수 없음`. Current Gemma4 references also distinguish the smaller E2B/E4B checkpoints as audio-capable while 31B is text/image, and vLLM source validates audio input only when a model has `audio_config`. Therefore 31B can remain the visual baseline, but 31B is not accepted as audio-native until a separate explicit-audio probe proves audio_config/audio token ingestion, and the current 31B `video_url` path has not done that.

## Candidate Rationale

`gemma4-e4b` is first because it is the closest same-family audio-capable model to the current Gemma/vLLM stack. vLLM documentation lists `google/gemma-4-E4B-it` as a 1x 24GB+ BF16 model and shows OpenAI-compatible audio handling. Its go/no-go gate is local startup plus explicit `input_audio` or `audio_url` WAV probes, not MP4 `video_url` success.

`gemma4-e2b` is second because it preserves the same family, modality support, and expected vLLM API shape while reducing local VRAM risk. It must pass the same native audio and cross-modal probes; startup alone is not enough.

`qwen2.5-omni` is third because it is a genuine unified audio/video candidate but has higher serving and fit risk on the local 2x RTX 4090 host. The matrix points first at a local quantized 7B route, with 3B as an alternate if fit or serving fails, and keeps Transformers as the documented native path unless vLLM parity is proven.

`local-asr-contingency` is fallback-only. It is degraded and non-native because audio becomes transcript text before the multimodal model sees it. It must not be chosen as primary and must not be presented as native audio understanding.

## Source Notes

Direct fetches for the Google model card/audio pages hit transport errors, so the decision used reachable search excerpts from those official pages plus vLLM docs/source, Qwen README, and local evidence. The official Google excerpts state Gemma4 E2B/E4B support text, image, and audio; 31B supports text and image only; audio is limited to the smaller models.

vLLM Gemma4 source says video is decomposed into timestamped image frames and audio is accepted only when the Hugging Face config has `audio_config`. This makes explicit audio payload acceptance the proof gate and explains why current 31B MP4 `video_url` is not native audio success.

Qwen2.5-Omni README documents text, image, audio, and video input with `Qwen2_5OmniProcessor`, `qwen_omni_utils.process_mm_info`, and consistent `use_audio_in_video`. Its BF16 memory table makes full 7B video risky on 24GB GPUs, so quantized 7B or 3B local routes are the honest fallback candidates.

## Guardrails For Later Tasks

Use only local inference for success evidence. Do not use cloud-hosted inference, hosted ASR, or hosted transcription. Do not benchmark as part of this decision task. Do not claim native audio support from `video_url` with embedded AAC; later probes must send explicit WAV audio via `input_audio` or `audio_url` and include no-audio ablations.

## Validation

Passed: matrix validation command from plan lines 175-184 loaded `.sisyphus/evidence/task-2-support-matrix.json`, found all required candidate names, and confirmed `local-asr-contingency` has `fallback_only: true`.

Passed: 31B exclusion grep from plan lines 188-190 matched this decision note because it explicitly says the current `google/gemma-4-31B-it` route is excluded from native audio success and references `audio_config` as the missing proof gate.
