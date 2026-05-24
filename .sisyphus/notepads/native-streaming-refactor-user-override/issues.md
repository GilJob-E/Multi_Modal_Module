# Issues

## 2026-05-22 Start Work
- Hook initially resumed paused legacy `audio-understanding-native-local`; Boulder state was corrected to active plan `native-streaming-refactor-user-override` because the immediate user-selected action was Start Work for native streaming refactor.
- `ast-grep` decorator search returned no matches for the initial pattern; direct grep and LSP symbols confirmed app endpoints and model classes.

## 2026-05-22 Timestamp Fix
- Added `recorded_at` to the override evidence artifact after orchestration review.

## 2026-05-22 Task 5 Parent Review Offset Fix
- Parent review found native generate passed `window.start_ms / 1000` as an ffmpeg seek offset into `window.host_path`, but that file is already the uploaded MP4 window rather than the original full timeline source.
- Fixed native generate to extract audio from `window.host_path` with `start_seconds=0` and keep `duration_seconds=window.duration_ms / 1000`; updated the fake extractor test expectation and refreshed Task 5 evidence.

## 2026-05-22 Task 7 Docs Write Gotcha
- A shell heredoc delimiter collision occurred while writing RUNBOOK text that itself contained a `PY` heredoc marker. Future doc writes should use a unique outer delimiter that cannot appear inside fenced command examples.
