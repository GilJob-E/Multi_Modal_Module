# Task 5 Qwen2.5-Omni Native AV No-Go

Generated: 2026-05-22T05:36:31.172140+00:00

## Branch Consistency

- Task 4 evidence: `.sisyphus/evidence/task-4-gemma4-native-probe.json`
- Task 4 `status`: `NO_GO`
- Branch decision: Qwen fallback is active because Task 4 status is exactly `NO_GO`; this decision does not rely on mere Task 4 file existence.

## Candidate Order Used

- Primary: `Qwen/Qwen2.5-Omni-7B-GPTQ-Int4`
- Alternate used: `Qwen/Qwen2.5-Omni-3B`
- Other documented alternates not needed after 3B produced controlled local probe evidence: `Qwen/Qwen2.5-Omni-7B-AWQ`, `Qwen/Qwen2.5-Omni-7B`
- Required success semantics: local-only native media ingestion where Qwen consumes direct audio media plus visual input. Transcript text, hosted ASR, hosted inference, remote Qwen APIs, and MP4 embedded audio alone do not count.

## Local Route Run

- Helper: `local-infer/tools/probe_qwen_omni_native.py`
- Command: `uv run --offline --with torch --with torchvision --with transformers --with qwen-omni-utils --with accelerate --with decord python local-infer/tools/probe_qwen_omni_native.py --fixtures .sisyphus/evidence/audio-fixtures --out .sisyphus/evidence/task-5-qwen-native-probe.json`
- Engine: Transformers + `qwen-omni-utils`, offline local files only.
- Media shape: each probe sent Qwen typed content parts with explicit WAV `audio` plus muted MP4 `video` plus prompt text; `use_audio_in_video=false`; no transcript text was supplied.
- Evidence JSON: `.sisyphus/evidence/task-5-qwen-native-probe.json`

## Local Inspection And Candidate Attempts

- Cached primary snapshot exists at `/home/kio/hf_cache/qwen-hub/models--Qwen--Qwen2.5-Omni-7B-GPTQ-Int4/snapshots/6d33b6bb5114a84de7efd38310779242520e7d4e`.
- Primary GPTQ load result: `load-no-go`, `ImportError: Loading a GPTQ quantized model requires optimum (`pip install optimum`)`.
- Cached alternate snapshot exists at `/home/kio/hf_cache/qwen-hub/models--Qwen--Qwen2.5-Omni-3B/snapshots/f75b40e3da2003cdd6e1829b1f420ca70797c34e`.
- Alternate 3B load result: model class `Qwen2_5OmniForConditionalGeneration`, processor class `Qwen2_5OmniProcessor`, load elapsed `8828.004` ms.
- Port `8003` remained unused because this task used the documented local Transformers route instead of a vLLM server route.

## Probe Result

- Overall status: `NO_GO`
- Required statuses: audio_positive=FAIL, no_audio_ablation=FAIL, beep_only=PASS, korean_phrase=FAIL, av_sync=PASS, cross_modal_event=PASS.
- Event latency: 1113.692 ms against 2000 ms budget.
- `all_required_passed`: `false`

## No-Go Reason

Qwen2.5-Omni did run locally with direct WAV audio and muted MP4 video media on the 3B alternate, but it did not pass all required probes. The primary GPTQ model could not initialize with the available local GPTQ runtime, and the 3B alternate failed the audio-positive, no-audio ablation, and Korean phrase checks. Because all required controlled probes did not pass, Qwen is not accepted as native AV fallback success.

This is not native success because the evidence records direct media ingestion but failing required outcomes. No transcript fusion, hosted ASR, hosted inference, remote Qwen API, manual listening, or text-only substitute was used or accepted.

## Cleanup

No Qwen server container or long-running process was started. The local Transformers process exited after writing evidence; existing unrelated containers were left untouched.
