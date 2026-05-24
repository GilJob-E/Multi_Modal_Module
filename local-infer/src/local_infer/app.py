from __future__ import annotations

# pyright: reportMissingImports=false

import base64
import binascii
import json
import os
import time
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .audio_analysis import analyze_wav_bytes
from .audio_store import AudioStore
from .frame_store import FrameStore
from .native_audio import NativeAudioExtractor
from .native_media_store import NativeMediaStore
from .native_payloads import DEFAULT_NATIVE_SYSTEM_PROMPT, build_native_chat_payload
from .payloads import DEFAULT_SYSTEM_PROMPT, build_chat_payload
from .vllm_client import default_vllm_client

MODEL = os.getenv("LOCAL_INFER_MODEL", "google/gemma-4-31B-it")


class FrameIn(BaseModel):
    timestamp_ms: int = Field(..., ge=0)
    frame_jpeg_base64: str = Field(..., min_length=1)


class GenerateIn(BaseModel):
    prompt: str = Field(..., min_length=1)
    n_frames: int = Field(5, ge=1, le=30)
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    max_tokens: int = Field(128, ge=1, le=1024)
    temperature: float = Field(0.2, ge=0.0, le=2.0)


class AudioIn(BaseModel):
    timestamp_ms: int = Field(..., ge=0)
    audio_wav_base64: str = Field(..., min_length=1)
    duration_ms: int = Field(..., ge=0)


class GenerateAvFallbackIn(BaseModel):
    prompt: str = Field(..., min_length=1)
    n_frames: int = Field(5, ge=1, le=30)
    audio_window_ms: int = Field(2000, ge=1, le=10000)
    max_tokens: int = Field(128, ge=1, le=1024)
    temperature: float = Field(0.2, ge=0.0, le=2.0)


class NativeWindowIn(BaseModel):
    start_ms: int = Field(..., ge=0)
    end_ms: int = Field(..., ge=0)
    video_mp4_base64: str
    mime_type: str = "video/mp4"


class NativeGenerateIn(BaseModel):
    prompt: str = Field(..., min_length=1)
    system_prompt: str = DEFAULT_NATIVE_SYSTEM_PROMPT
    max_tokens: int = Field(128, ge=1, le=1024)
    temperature: float = Field(0.2, ge=0.0, le=2.0)
    model: str | None = None
    stream: bool = True


class FrameStored(BaseModel):
    session_id: str
    stored_frames: int


class AudioStored(BaseModel):
    session_id: str
    stored_audio_chunks: int
    stored_audio_duration_ms: int


class NativeWindowStored(BaseModel):
    session_id: str
    stored_windows: int
    latest_sha256: str
    latest_duration_ms: int
    latest_video_url: str


def _sse_event(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def create_app(
    *,
    vllm_client=None,
    max_frames_per_session: int = 30,
    max_audio_chunks_per_session: int = 20,
    native_media_store: NativeMediaStore | None = None,
    native_audio_extractor: NativeAudioExtractor | None = None,
    native_media_dir: str | None = None,
    native_media_url_prefix: str | None = None,
    max_native_windows_per_session: int = 6,
    max_native_bytes_per_session: int = 200 * 1024 * 1024,
) -> FastAPI:
    app = FastAPI(title="GilJob Local Gemma4 Inference Gateway", version="0.1.0")
    store = FrameStore(max_frames_per_session=max_frames_per_session)
    audio_store = AudioStore(max_chunks_per_session=max_audio_chunks_per_session)
    native_host_dir = native_media_dir or os.getenv("LOCAL_INFER_NATIVE_MEDIA_DIR", "/tmp/gje-local-infer-native-media")
    native_url_prefix = native_media_url_prefix or os.getenv(
        "LOCAL_INFER_NATIVE_MEDIA_URL_PREFIX", f"file://{native_host_dir}"
    )
    media_store = native_media_store or NativeMediaStore(
        runtime_dir=native_host_dir,
        url_prefix=native_url_prefix,
        max_windows_per_session=max_native_windows_per_session,
        max_total_bytes=max_native_bytes_per_session,
        max_window_bytes=max_native_bytes_per_session,
    )
    extractor = native_audio_extractor or NativeAudioExtractor()
    client = vllm_client or default_vllm_client()

    @app.get("/v1/health")
    def health() -> dict[str, Any]:
        try:
            models = client.health() if hasattr(client, "health") else {"status": "unknown"}
            return {"ok": True, "model": MODEL, "vllm": models}
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/v1/sessions/{session_id}/frames", response_model=FrameStored)
    def add_frame(session_id: str, frame: FrameIn) -> FrameStored:
        store.add_frame(
            session_id=session_id,
            timestamp_ms=frame.timestamp_ms,
            frame_jpeg_base64=frame.frame_jpeg_base64,
        )
        return FrameStored(
            session_id=session_id,
            stored_frames=len(store.get_recent_frames(session_id, max_frames_per_session)),
        )

    @app.post("/v1/sessions/{session_id}/audio", response_model=AudioStored)
    def add_audio(session_id: str, audio: AudioIn) -> AudioStored:
        try:
            analyze_wav_bytes(base64.b64decode(audio.audio_wav_base64, validate=True))
            audio_store.add_chunk(
                session_id=session_id,
                timestamp_ms=audio.timestamp_ms,
                audio_wav_base64=audio.audio_wav_base64,
                duration_ms=audio.duration_ms,
            )
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return AudioStored(
            session_id=session_id,
            stored_audio_chunks=len(audio_store.get_recent_chunks(session_id)),
            stored_audio_duration_ms=audio_store.total_duration_ms(session_id),
        )

    @app.post("/v1/sessions/{session_id}/generate")
    def generate(session_id: str, req: GenerateIn) -> StreamingResponse:
        frames = store.get_recent_frames(session_id, req.n_frames)
        if not frames:
            raise HTTPException(status_code=400, detail="no frames stored for session")
        payload = build_chat_payload(
            model=MODEL,
            frames=frames,
            prompt=req.prompt,
            system_prompt=req.system_prompt,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
            stream=True,
        )

        def events():
            t0 = time.perf_counter()
            first = True
            chunks: list[str] = []
            for token in client.stream_chat(payload):
                chunks.append(token)
                if first:
                    first = False
                    yield _sse_event({"type": "ttft", "ttft_ms": round((time.perf_counter() - t0) * 1000, 1)})
                yield _sse_event({"type": "token", "text": token})
            yield _sse_event(
                {
                    "type": "final",
                    "text": "".join(chunks),
                    "frames_used": len(frames),
                    "total_ms": round((time.perf_counter() - t0) * 1000, 1),
                }
            )

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.post("/v1/sessions/{session_id}/generate-av-fallback")
    def generate_av_fallback(session_id: str, req: GenerateAvFallbackIn) -> StreamingResponse:
        frames = store.get_recent_frames(session_id, req.n_frames)
        if not frames:
            raise HTTPException(status_code=400, detail="no frames stored for session")
        audio_chunks = audio_store.get_window(session_id, req.audio_window_ms)
        if not audio_chunks:
            raise HTTPException(status_code=400, detail="no audio stored for session")

        latest_audio = audio_chunks[-1]
        try:
            audio_analysis = analyze_wav_bytes(latest_audio.wav_bytes)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        audio_analysis_dict = audio_analysis.to_dict()
        audio_used_ms = min(sum(chunk.duration_ms for chunk in audio_chunks), req.audio_window_ms)

        def events():
            t0 = time.perf_counter()
            response_text = _build_degraded_fallback_text(
                prompt=req.prompt,
                frames_used=len(frames),
                audio_analysis=audio_analysis_dict,
            )
            yield _sse_event({"type": "ttft", "ttft_ms": round((time.perf_counter() - t0) * 1000, 1)})
            yield _sse_event({"type": "token", "text": response_text})
            yield _sse_event(
                {
                    "type": "final",
                    "text": response_text,
                    "fallback_mode": "degraded_local_audio_analysis",
                    "native_success": False,
                    "audio_analysis": audio_analysis_dict,
                    "audio_used_ms": audio_used_ms,
                    "frames_used": len(frames),
                    "total_ms": round((time.perf_counter() - t0) * 1000, 1),
                }
            )

        return StreamingResponse(events(), media_type="text/event-stream")

    # Native streaming endpoints begin
    @app.post("/v1/native/sessions/{session_id}/windows", response_model=NativeWindowStored)
    def add_native_window(session_id: str, window: NativeWindowIn) -> NativeWindowStored:
        try:
            stored = media_store.add_window(
                session_id=session_id,
                start_ms=window.start_ms,
                end_ms=window.end_ms,
                video_mp4_base64=window.video_mp4_base64,
                mime_type=window.mime_type,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return NativeWindowStored(
            session_id=session_id,
            stored_windows=len(media_store.get_recent_windows(session_id)),
            latest_sha256=stored.sha256,
            latest_duration_ms=stored.duration_ms,
            latest_video_url=stored.file_url,
        )

    @app.post("/v1/native/sessions/{session_id}/generate")
    def generate_native(session_id: str, req: NativeGenerateIn) -> StreamingResponse:
        if not req.stream:
            raise HTTPException(status_code=400, detail="native generate is SSE-only; stream must be true")
        window = media_store.latest(session_id)
        if window is None:
            raise HTTPException(status_code=400, detail="no native window stored for session")
        try:
            input_audio = extractor.extract_window(
                window.host_path,
                start_seconds=0,
                duration_seconds=window.duration_ms / 1000,
            )
            payload = build_native_chat_payload(
                model=req.model or MODEL,
                video_file_url=window.file_url,
                input_audio=input_audio,
                prompt=req.prompt,
                system_prompt=req.system_prompt,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
                stream=True,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        def events():
            t0 = time.perf_counter()
            first = True
            chunks: list[str] = []
            for token in client.stream_chat(payload):
                chunks.append(token)
                if first:
                    first = False
                    yield _sse_event({"type": "ttft", "ttft_ms": round((time.perf_counter() - t0) * 1000, 1)})
                yield _sse_event({"type": "token", "text": token})
            yield _sse_event(
                {
                    "type": "final",
                    "text": "".join(chunks),
                    "native_media_mode": "video_url_plus_input_audio",
                    "video_sha256": window.sha256,
                    "video_url": window.file_url,
                    "input_audio_present": True,
                    "fallback_used": False,
                    "total_ms": round((time.perf_counter() - t0) * 1000, 1),
                }
            )

        return StreamingResponse(events(), media_type="text/event-stream")

    # Native streaming endpoints end

    return app


def _build_degraded_fallback_text(
    *,
    prompt: str,
    frames_used: int,
    audio_analysis: dict[str, Any],
) -> str:
    if audio_analysis["vocal_cue_detected"]:
        cue = "a sustained 아~/ah-like vocal cue"
    elif audio_analysis["beep_tone_detected"]:
        cue = "a beep/tone cue"
    elif audio_analysis["silence_detected"]:
        cue = "silence/no-audio"
    else:
        cue = "local audio energy without a known cue class"
    return (
        "Degraded non-native fallback: "
        f"using {frames_used} recent visual frame(s) plus deterministic local WAV analysis, "
        f"I detected {cue}. Prompt: {prompt}"
    )


app = create_app()
