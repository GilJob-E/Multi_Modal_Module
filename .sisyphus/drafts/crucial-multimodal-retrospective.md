# Crucial Retrospective: GilJob Native Multimodal Testing

## Permanent Operating Lessons
- Use `/home/kio/workspace/gje/vid_0033.mp4` as the real user-provided multimodal test fixture for future GilJob audio/video validation.
- Do not present synthetic fixtures as product proof. Synthetic fixtures are only harness smoke tests unless explicitly labeled otherwise.
- Keep native AV success, model-serving readiness, model-quality probe failure, and degraded fallback as separate states.
- Never relabel ASR/rule/VAD/audio-analysis fallback as native multimodal audio/video understanding.
- For the practical target, success means: real visual cue + real vocal cue from the real fixture, with response around the 2-second budget.

## Why the Prior Work Disappointed
- It over-indexed on synthetic `cross_modal_event` fixtures instead of a real user-provided video.
- It accumulated no-go/fallback evidence while the user's desired proof was direct native AV behavior.
- It allowed degraded local audio analysis to become too prominent despite `native_success=false`.
- It did not state early and bluntly enough that the current `local-infer` path is frame-centric (`/frames` + `/generate`) rather than native audio/video.
- It treated server readiness timeout evidence too close to a route no-go, even though readiness failure is not model capability failure.

## Gemma4 Native Status Correction
- Current Gemma4 E4B/E2B evidence is **not** a native audio capability failure.
- Evidence says the vLLM server did not become request-ready at `/v1/models` within the configured window, so the native audio probes were not actually sent.
- Existing evidence records `readiness timeout after 900s; last=[Errno 104] Connection reset by peer` in `.sisyphus/evidence/task-4-gemma4-no-go.md`.
- The probe script default is `--startup-timeout 600`, but the recorded run used/recorded 900 seconds for readiness failure.
- Conclusion: classify Gemma4 as **serving/runtime readiness unresolved; retry/debug required**, not as a failed native model.

## Next Plan Implication
- A revised Gemma4 validation plan should use the real fixture, longer/warm readiness windows, better startup telemetry, cached retry handling, and only declare capability failure after the server is ready and explicit audio/video probes fail.
