# Decisions

## 2026-05-22 Start Work
- Execute from `.sisyphus/plans/native-streaming-refactor-user-override.md`.
- Keep `audio-understanding-native-local-legacy` paused in `boulder.json`.
- Wave 1 dispatch: Task 1 override evidence, Task 2 native MP4 window store, Task 3 same-window native audio transport.

## 2026-05-22 Task 5 Native App Endpoints
- `create_app` keeps native dependencies injectable for tests and defaults runtime media storage to `LOCAL_INFER_NATIVE_MEDIA_DIR` with `LOCAL_INFER_NATIVE_MEDIA_URL_PREFIX` or local `file://` mapping.
- Native upload validation maps store business-rule `ValueError`s to HTTP 400 while leaving unrelated FastAPI/Pydantic structural errors to the framework.
