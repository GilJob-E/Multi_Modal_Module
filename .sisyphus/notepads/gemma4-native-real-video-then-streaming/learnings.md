# Learnings

## 2026-05-21 Start Work
- User target is fixed: Gemma4 native multimodal proof on `/home/kio/workspace/gje/vid_0033.mp4` first; streaming refactor only after proof gate passes.
- Do not count Qwen, ASR/VAD/rule fallback, synthetic media, frame-only path, or degraded endpoints as success.
- vLLM accepts local media via `file://` when `--allowed-local-media-path` points to an existing directory; paths must resolve under that directory and non-subpaths are rejected.
- For Gemma 4, E2B/E4B are the audio-capable variants; the 31B recipe shows text/image/video, while the audio section explicitly calls out E2B and E4B.
- Local media loads bypass HTTP fetch timeouts; only HTTP image/video URLs use `VLLM_IMAGE_FETCH_TIMEOUT` (5s default) and `VLLM_VIDEO_FETCH_TIMEOUT` (30s default).
- Container guidance for Gemma 4 uses `--ipc=host` plus `--shm-size 16G` (and `--network host`) to avoid shared-memory pressure during multimodal serving.
- The proof gate verifier is a standalone stdlib CLI at `local-infer/tools/verify_vid0033_native_proof.py`; it exits nonzero on `proof_invalid` and still writes the classified JSON artifact.
- The known degraded fallback artifact `.sisyphus/evidence/task-10-audio-analysis.json` is rejected because the raw JSON contains forbidden markers such as `/audio`, `audio_analysis`, and `cross_modal_event`.

- 2026-05-21 Task 1: ffprobe on `/home/kio/workspace/gje/vid_0033.mp4` confirmed one H.264 video stream, one MP3 audio stream, 640x480, 30/1 fps, and ~50.29s duration.
- Task 1 evidence now includes SHA256 and an explicit real-fixture-only statement; synthetic product proof remains forbidden.

## 2026-05-21 Task 4 Readiness Hardening
- Hardened `probe_gemma4_vllm_sequence.py` now builds Gemma4 E4B/E2B launch commands with `/home/kio/workspace/gje:/workspace/gje:ro`, `--allowed-local-media-path /workspace/gje`, `VLLM_ENGINE_READY_TIMEOUT_S=3600`, `--ipc=host`, `--shm-size 16G`, and `--limit-mm-per-prompt {"video":1,"audio":1,"image":4}`.
- Dry-run readiness evidence at `.sisyphus/evidence/vid0033-gemma4-readiness.json` classifies unlaunched readiness as `serving_runtime_unresolved`, preserving the rule that readiness timeouts are serving-runtime unresolved rather than Gemma4 capability no-go.

## 2026-05-21 Task 2 Ground Truth Package
- Built `.sisyphus/evidence/vid0033-ground-truth.json` from the real `/home/kio/workspace/gje/vid_0033.mp4` fixture only, copying SHA/source identity from `vid0033-media-metadata.json`.
- Visual evidence frames show one stable indoor front-facing speaker scene; assertions are conservative and avoid identity or exact speech claims.
- Local audio diagnostics show sustained non-silent speech-like activity through most of the clip, with ffmpeg silencedetect quiet intervals around 0.478-1.364s and 48.176s-end. Exact transcript text was not asserted.

## 2026-05-21 Task 3 Real Video Harness
- `probe_gemma4_real_video.py` uses a stdlib OpenAI-compatible `/v1/chat/completions` payload with the locked `file:///workspace/gje/vid_0033.mp4` URL and keeps ground-truth diagnostics out of the model prompt.
- The dry-run success artifact intentionally omits literal forbidden-marker lists so `verify_vid0033_native_proof.py` will not reject a future pass solely because guardrail terms appear as metadata.
- Wrong fixture URLs are rejected before network I/O; the sample path dry run writes `proof_invalid` and exits nonzero.

## 2026-05-21 19:04 UTC Task 6 Native Proof Gate
- E4B (`google/gemma-4-E4B-it`) reached local vLLM `/v1/models` readiness on port 8002 with `/home/kio/workspace/gje:/workspace/gje:ro`, `--allowed-local-media-path /workspace/gje`, and `VLLM_ENGINE_READY_TIMEOUT_S=3600`; E2B was not attempted because E4B was not serving/runtime unresolved.
- The real native proof request used `file:///workspace/gje/vid_0033.mp4` and `.sisyphus/evidence/vid0033-ground-truth.json`; output artifacts are `.sisyphus/evidence/vid0033-gemma4-readiness.json`, `.sisyphus/evidence/vid0033-gemma4-native-proof.json`, and `.sisyphus/evidence/vid0033-native-proof-gate.json`.
- Final gate status is `gemma4_capability_no_go` with `streaming_refactor_allowed=false`; Tasks 7-9 remain blocked.

## 2026-05-21 19:18 UTC Task 6 Revised Native AV Attempt
- `probe_gemma4_real_video.py` now supports `--audio-url` for `--mode video_plus_audio_from_same_fixture`; the dry-run evidence shows both `video_url=file:///workspace/gje/vid_0033.mp4` and `audio_url=file:///workspace/gje/.sisyphus/evidence/vid0033-soundtrack.wav` in `media_content_parts`.
- Extracted the same-fixture soundtrack to `.sisyphus/evidence/vid0033-soundtrack.wav` as mono 16 kHz `pcm_s16le` WAV; provenance is in `.sisyphus/evidence/vid0033-soundtrack-provenance.json` with source SHA `139e6b4cc725b0a4836baffde1e811b5cf41271e2a5ac0fa6f4dec41645cd4a8` and output SHA `9bd4cc0e1b7054ecf5a3a234abcad8b79063b5379bd5956a87adc0749059948e`.
- E4B reached readiness again for the revised AV attempt, so E2B was not attempted.

## 2026-05-21 19:30 UTC Task 6 Audio Dependency Serving Retry
- Preflight inside `vllm/vllm-openai:nightly` installed `av` and `soundfile`, then `vllm.multimodal.media.audio.load_audio('/workspace/gje/.sisyphus/evidence/vid0033-soundtrack.wav')` succeeded with `loaded (804589,) 16000 float32`.
- E4B was launched with `av`/`soundfile` install plus the same `load_audio` startup probe before `vllm serve`; readiness evidence records both dependency proof paths and the hardened launch settings.
- With dependencies present, the revised native AV request was accepted (`raw_response.http_status=200`), changing the blocker from schema/media failure to accepted-request capability no-go.

## 2026-05-21 19:41 UTC Task 6 Time-Window AV Prompt Retry
- `probe_gemma4_real_video.py` now uses `PROMPT_VERSION=time_window_av_v2` and asks for compact JSON with `visual_observations`, `audio_timeline`, `cross_modal_observations`, `uncertainty`, and `do_not_transcribe_unless_clearly_audible`.
- The prompt requests independent classification for windows `0_2s`, `12_17s`, and `48_50s` without revealing expected classifications; request traces now record `prompt_version` and `prompt_shape`.
- The evaluator now parses the assistant JSON timeline, requires actual 12-17s speech-like activity plus a 48-50s quiet/silent/non-speech observation, and rejects prompt-label echo as insufficient.
## 2026-05-21 20:00 UTC Task 6 Windowed Native AV Retry
- Extracted three neutral same-fixture mono 16 kHz WAV windows from `/home/kio/workspace/gje/vid_0033.mp4`: `.sisyphus/evidence/vid0033-window-000000-002000.wav`, `.sisyphus/evidence/vid0033-window-012000-017000.wav`, and `.sisyphus/evidence/vid0033-window-048176-050286.wav`; provenance is `.sisyphus/evidence/vid0033-window-provenance.json`.
- `probe_gemma4_real_video.py` now supports `--mode video_plus_windowed_soundtracks`, `PROMPT_VERSION=windowed_native_v3`, and a request shape with exactly one original `video_url` plus exactly three locked window `audio_url` parts; dry-run assertions confirmed no full-soundtrack media/provenance in the segmented request trace.
- E4B launched with `--limit-mm-per-prompt {"video":1,"audio":3,"image":4}` and `av`/`soundfile`; startup `load_audio` succeeded for all three window WAVs with shapes `(32000,)`, `(80000,)`, and `(33760,)` at 16000 Hz.

## 2026-05-21 20:12 UTC Task 6 Window-Pack Native AV Final Attempt
- Created `.sisyphus/evidence/vid0033-window-pack.wav` by direct ffmpeg concat of the three existing same-fixture window WAVs in chronological order; provenance is `.sisyphus/evidence/vid0033-window-pack-provenance.json` with source MP4 SHA, source window SHAs, output SHA `21adc16dea56443b46466b736484c5f7aaa01e60c6e2a81b24c11f9ec7737e66`, ffprobe duration `9.110000`, and an explicit no transcript/ASR/fallback/synthetic-media statement.
- `probe_gemma4_real_video.py` now supports `--mode video_plus_window_pack_soundtrack` with `PROMPT_VERSION=window_pack_native_v4`, exactly one original `video_url`, exactly one window-pack `audio_url`, request trace media order, and window-pack provenance.
- E4B launched with `av`/`soundfile`, startup `load_audio('/workspace/gje/.sisyphus/evidence/vid0033-window-pack.wav')` succeeded with shape `(145760,)` at 16000 Hz, and the proof request returned HTTP 200.

## 2026-05-21T20:29:54.733192+00:00 Task: final-verification-wave
Final review wave passed after resolving one context-mining blocker. The stale `.sisyphus/evidence/task-6-gemma4-vllm-startup.log` preserved older pass/allowance stdout, so it now starts with a supersession notice pointing to the final current gate: `gemma4_capability_no_go`, `streaming_refactor_allowed=false`. Top-level `README.md` and `INFERENCE_PIPELINE.md` also state the current no-go stop-state and cancelled/not-executed streaming refactor.
