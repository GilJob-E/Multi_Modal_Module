# Task 10 final state

## Gate status

Gate status is `gemma4_capability_no_go`. `streaming_refactor_allowed=false`.

The fixed real proof fixture is `/home/kio/workspace/gje/vid_0033.mp4`.

## Accepted native request

The final accepted native request used `google/gemma-4-E4B-it`, mode `video_plus_window_pack_soundtrack`, prompt version `window_pack_native_v4`, the real fixture, and native media. vLLM returned HTTP 200, so this was not a readiness or schema failure.

Visual check passed. The 12-17s mid-window speech-like activity was detected. The proof gate still failed because Gemma4 classified the final 48.176-50.286s quiet-tail window as `speech`. That failed the audio and cross-modal checks.

## Stop-state

Gemma4 native proof did not pass. streaming refactor cancelled and not executed. Native rolling MP4 endpoints are not available.

Qwen, synthetic fixtures, ASR/VAD/rule fallback, transcript-as-proof, frame-only paths, and degraded fallback endpoints are not Gemma4 native success. fallback paths are not native proof.

## Evidence

- `.sisyphus/evidence/vid0033-gemma4-native-proof.json`
- `.sisyphus/evidence/vid0033-native-proof-gate.json`
- `.sisyphus/evidence/task-7-9-streaming-refactor-blocked.json`
- `.sisyphus/evidence/vid0033-window-pack-provenance.json`

## Verification

Docs and evidence are expected to pass the grep QA, the final-state consistency Python QA, and the local-infer test command:

```bash
cd /home/kio/workspace/gje && grep -R -E "vid_0033.mp4|native proof gate|streaming_refactor_allowed|fallback.*not.*native" local-infer/docs local-infer/README.md .sisyphus/evidence/task-10-final-state.md
cd /home/kio/workspace/gje && python3 - <<'PY'
import json, pathlib
gate=json.load(open('.sisyphus/evidence/vid0033-native-proof-gate.json'))
text=pathlib.Path('.sisyphus/evidence/task-10-final-state.md').read_text()
if gate['streaming_refactor_allowed']:
    assert 'streaming refactor executed' in text or 'native rolling' in text
else:
    assert 'streaming refactor cancelled' in text or 'not executed' in text
PY
cd /home/kio/workspace/gje/local-infer && PYTHONPATH=src uv run --with pytest --with httpx pytest tests -q
```
