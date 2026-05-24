
## Task 2 Candidate Order - 2026-05-22

- Recorded deterministic order in `.sisyphus/evidence/task-2-support-matrix.json`: Gemma4 E4B, Gemma4 E2B, Qwen2.5-Omni, then local ASR contingency only after native no-go evidence.
- Local ASR is explicitly `fallback_only=true` and is not native success because transcript text replaces model audio-token ingestion.
- Decision note explicitly excludes current `google/gemma-4-31B-it` MP4 `video_url` route from native audio success until an explicit-audio `audio_config` proof exists.
- Task 3: Fixture speech probes are deterministic tone-coded WAV controls, not human-spoken samples; the manifest records this limitation to avoid pretending local TTS/ASR was used.
