# pyright: reportMissingImports=false
import base64
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from local_infer.app import create_app


FIXTURES = Path(__file__).resolve().parents[2] / ".sisyphus" / "evidence" / "audio-fixtures"


class FakeVllmClient:
    def __init__(self):
        self.payloads = []

    def stream_chat(self, payload):
        self.payloads.append(payload)
        yield "좋"
        yield "아요"


def test_frames_endpoint_stores_session_frames_and_reports_count():
    fake = FakeVllmClient()
    client = TestClient(create_app(vllm_client=fake, max_frames_per_session=5))

    r = client.post(
        "/v1/sessions/s1/frames",
        json={"timestamp_ms": 1000, "frame_jpeg_base64": base64.b64encode(b"jpg").decode()},
    )

    assert r.status_code == 200
    assert r.json() == {"session_id": "s1", "stored_frames": 1}


def test_generate_stream_uses_recent_frames_and_streams_tokens_as_sse():
    fake = FakeVllmClient()
    client = TestClient(create_app(vllm_client=fake, max_frames_per_session=5))
    for i in range(3):
        client.post(
            "/v1/sessions/s1/frames",
            json={
                "timestamp_ms": i * 1000,
                "frame_jpeg_base64": base64.b64encode(f"jpg-{i}".encode()).decode(),
            },
        )

    with client.stream(
        "POST",
        "/v1/sessions/s1/generate",
        json={"prompt": "질문", "n_frames": 2, "max_tokens": 16},
    ) as r:
        body = r.read().decode()

    assert r.status_code == 200
    assert '"type": "ttft"' in body
    assert '"type": "token", "text": "좋"' in body
    assert '"type": "token", "text": "아요"' in body
    assert '"type": "final", "text": "좋아요"' in body
    payload = fake.payloads[0]
    content = payload["messages"][1]["content"]
    assert len([p for p in content if p["type"] == "image_url"]) == 2
    assert content[-1] == {"type": "text", "text": "질문"}
    assert payload["max_tokens"] == 16


def test_audio_endpoint_stores_wav_chunks_and_reports_duration():
    fake = FakeVllmClient()
    client = TestClient(create_app(vllm_client=fake, max_audio_chunks_per_session=5))
    wav_b64 = base64.b64encode((FIXTURES / "cross_modal_event.wav").read_bytes()).decode()

    response = client.post(
        "/v1/sessions/s1/audio",
        json={"timestamp_ms": 1200, "audio_wav_base64": wav_b64, "duration_ms": 2600},
    )

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "s1",
        "stored_audio_chunks": 1,
        "stored_audio_duration_ms": 2600,
    }


def test_generate_av_fallback_detects_visual_context_and_vocal_cue_without_native_claim():
    fake = FakeVllmClient()
    client = TestClient(create_app(vllm_client=fake, max_frames_per_session=5))
    for timestamp, relative_path in [
        (0, "frames/cross_modal_event/0000_start.jpg"),
        (1000, "frames/cross_modal_event/1000_look_up_sky_arrow.jpg"),
    ]:
        client.post(
            "/v1/sessions/s1/frames",
            json={
                "timestamp_ms": timestamp,
                "frame_jpeg_base64": base64.b64encode((FIXTURES / relative_path).read_bytes()).decode(),
            },
        )
    client.post(
        "/v1/sessions/s1/audio",
        json={
            "timestamp_ms": 0,
            "audio_wav_base64": base64.b64encode((FIXTURES / "cross_modal_event.wav").read_bytes()).decode(),
            "duration_ms": 2600,
        },
    )

    with client.stream(
        "POST",
        "/v1/sessions/s1/generate-av-fallback",
        json={"prompt": "Use both image and audio. What cue happened?", "n_frames": 2, "audio_window_ms": 3000},
    ) as response:
        body = response.read().decode()

    assert response.status_code == 200
    events = parse_sse_events(body)
    final = events[-1]
    assert final["type"] == "final"
    assert final["fallback_mode"] == "degraded_local_audio_analysis"
    assert final["native_success"] is False
    assert final["frames_used"] == 2
    assert final["audio_analysis"]["vocal_cue_detected"] is True
    assert "Degraded non-native fallback" in final["text"]
    assert "아~/ah-like" in final["text"]
    assert fake.payloads == []


def test_generate_av_fallback_returns_400_when_audio_missing():
    fake = FakeVllmClient()
    client = TestClient(create_app(vllm_client=fake, max_frames_per_session=5))
    client.post(
        "/v1/sessions/s1/frames",
        json={
            "timestamp_ms": 0,
            "frame_jpeg_base64": base64.b64encode((FIXTURES / "frames/cross_modal_event/0000_start.jpg").read_bytes()).decode(),
        },
    )

    response = client.post(
        "/v1/sessions/s1/generate-av-fallback",
        json={"prompt": "질문", "n_frames": 1, "audio_window_ms": 2000},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "no audio stored for session"


def test_frame_only_generate_still_uses_vllm_payload_not_audio_fallback():
    fake = FakeVllmClient()
    client = TestClient(create_app(vllm_client=fake, max_frames_per_session=5))
    client.post(
        "/v1/sessions/s1/frames",
        json={"timestamp_ms": 1000, "frame_jpeg_base64": base64.b64encode(b"frame-only").decode()},
    )

    with client.stream(
        "POST",
        "/v1/sessions/s1/generate",
        json={"prompt": "기존 경로", "n_frames": 1},
    ) as response:
        body = response.read().decode()

    assert response.status_code == 200
    assert '"fallback_mode"' not in body
    assert len(fake.payloads) == 1


def parse_sse_events(body: str) -> list[dict[str, Any]]:
    events = []
    for block in body.strip().split("\n\n"):
        if block.startswith("data: "):
            events.append(json.loads(block.removeprefix("data: ")))
    return events
