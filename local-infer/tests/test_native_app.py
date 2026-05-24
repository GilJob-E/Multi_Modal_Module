# pyright: reportMissingImports=false
import base64
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from local_infer.app import create_app
from local_infer.native_audio import NativeInputAudio


class FakeVllmClient:
    def __init__(self):
        self.payloads = []
        self.stream_calls = 0

    def stream_chat(self, payload):
        self.stream_calls += 1
        self.payloads.append(payload)
        yield "네"
        yield " 좋습니다"


class FakeNativeAudioExtractor:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.calls = []

    def extract_window(self, source_mp4_path, *, start_seconds: float, duration_seconds: float):
        self.calls.append(
            {
                "source_mp4_path": str(source_mp4_path),
                "start_seconds": start_seconds,
                "duration_seconds": duration_seconds,
            }
        )
        if self.fail:
            raise ValueError("native extraction failed")
        return NativeInputAudio.from_wav_bytes(b"wav-bytes")


def mp4_b64(data: bytes = b"fake-mp4") -> str:
    return base64.b64encode(data).decode("ascii")


def parse_sse_events(body: str) -> list[dict[str, Any]]:
    events = []
    for block in body.strip().split("\n\n"):
        if block.startswith("data: "):
            events.append(json.loads(block.removeprefix("data: ")))
    return events


def user_content_parts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return payload["messages"][1]["content"]


def test_native_window_upload_stores_mp4_and_reports_latest(tmp_path: Path):
    fake = FakeVllmClient()
    client = TestClient(create_app(vllm_client=fake, native_media_dir=str(tmp_path), native_media_url_prefix="file:///native"))

    response = client.post(
        "/v1/native/sessions/native-s1/windows",
        json={"start_ms": 12000, "end_ms": 17000, "video_mp4_base64": mp4_b64(), "mime_type": "video/mp4"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "native-s1"
    assert body["stored_windows"] == 1
    assert body["latest_duration_ms"] == 5000
    assert body["latest_video_url"].startswith("file:///native/native-s1/")
    assert len(body["latest_sha256"]) == 64


def test_native_generate_streams_latest_window_with_video_url_and_input_audio(tmp_path: Path):
    fake = FakeVllmClient()
    extractor = FakeNativeAudioExtractor()
    client = TestClient(
        create_app(
            vllm_client=fake,
            native_audio_extractor=extractor,
            native_media_dir=str(tmp_path),
            native_media_url_prefix="file:///native",
        )
    )
    upload = client.post(
        "/v1/native/sessions/native-s1/windows",
        json={"start_ms": 12000, "end_ms": 17000, "video_mp4_base64": mp4_b64(b"first"), "mime_type": "video/mp4"},
    )
    client.post(
        "/v1/native/sessions/native-s1/windows",
        json={"start_ms": 20000, "end_ms": 23000, "video_mp4_base64": mp4_b64(b"latest"), "mime_type": "video/mp4"},
    )

    with client.stream(
        "POST",
        "/v1/native/sessions/native-s1/generate",
        json={"prompt": "후속 질문", "max_tokens": 16, "temperature": 0.1},
    ) as response:
        body = response.read().decode()

    assert upload.status_code == 200
    assert response.status_code == 200
    events = parse_sse_events(body)
    assert [event["type"] for event in events] == ["ttft", "token", "token", "final"]
    final = events[-1]
    assert final["text"] == "네 좋습니다"
    assert final["native_media_mode"] == "video_url_plus_input_audio"
    assert final["input_audio_present"] is True
    assert final["fallback_used"] is False
    assert final["video_url"].startswith("file:///native/native-s1/20000-23000-")
    video_filename = Path(fake.payloads[0]["messages"][1]["content"][0]["video_url"]["url"]).name
    assert final["video_sha256"] == video_filename.split("-")[2]
    assert isinstance(final["total_ms"], float)

    assert fake.stream_calls == 1
    payload = fake.payloads[0]
    assert payload["max_tokens"] == 16
    assert payload["temperature"] == 0.1
    parts = user_content_parts(payload)
    assert [part["type"] for part in parts] == ["video_url", "input_audio", "text"]
    assert parts[0]["video_url"]["url"] == final["video_url"]
    assert parts[1]["input_audio"]["format"] == "wav"
    assert parts[2] == {"type": "text", "text": "후속 질문"}
    assert "image_url" not in repr(payload)
    assert extractor.calls == [
        {
            "source_mp4_path": str(next((tmp_path / "native-s1").glob("20000-23000-*.mp4"))),
            "start_seconds": 0,
            "duration_seconds": 3.0,
        }
    ]


def test_native_generate_returns_400_when_no_window(tmp_path: Path):
    client = TestClient(create_app(vllm_client=FakeVllmClient(), native_media_dir=str(tmp_path)))

    response = client.post("/v1/native/sessions/missing/generate", json={"prompt": "질문"})

    assert response.status_code == 400
    assert response.json()["detail"] == "no native window stored for session"


def test_native_generate_returns_400_when_stream_false(tmp_path: Path):
    client = TestClient(create_app(vllm_client=FakeVllmClient(), native_media_dir=str(tmp_path)))
    client.post(
        "/v1/native/sessions/native-s1/windows",
        json={"start_ms": 0, "end_ms": 1000, "video_mp4_base64": mp4_b64(), "mime_type": "video/mp4"},
    )

    response = client.post("/v1/native/sessions/native-s1/generate", json={"prompt": "질문", "stream": False})

    assert response.status_code == 400
    assert response.json()["detail"] == "native generate is SSE-only; stream must be true"


def test_native_generate_returns_400_on_extraction_failure(tmp_path: Path):
    fake = FakeVllmClient()
    client = TestClient(
        create_app(
            vllm_client=fake,
            native_audio_extractor=FakeNativeAudioExtractor(fail=True),
            native_media_dir=str(tmp_path),
        )
    )
    client.post(
        "/v1/native/sessions/native-s1/windows",
        json={"start_ms": 0, "end_ms": 1000, "video_mp4_base64": mp4_b64(), "mime_type": "video/mp4"},
    )

    response = client.post("/v1/native/sessions/native-s1/generate", json={"prompt": "질문"})

    assert response.status_code == 400
    assert response.json()["detail"] == "native extraction failed"
    assert fake.payloads == []


def test_native_window_upload_returns_400_for_wrong_mime(tmp_path: Path):
    client = TestClient(create_app(vllm_client=FakeVllmClient(), native_media_dir=str(tmp_path)))

    response = client.post(
        "/v1/native/sessions/native-s1/windows",
        json={"start_ms": 0, "end_ms": 1000, "video_mp4_base64": mp4_b64(), "mime_type": "video/quicktime"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "mime_type must be video/mp4"


def test_native_window_upload_returns_400_for_empty_decoded_mp4(tmp_path: Path):
    client = TestClient(create_app(vllm_client=FakeVllmClient(), native_media_dir=str(tmp_path)))

    response = client.post(
        "/v1/native/sessions/native-s1/windows",
        json={"start_ms": 0, "end_ms": 1000, "video_mp4_base64": "", "mime_type": "video/mp4"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "decoded video bytes are required"


def test_native_window_upload_returns_400_for_max_bytes(tmp_path: Path):
    client = TestClient(
        create_app(vllm_client=FakeVllmClient(), native_media_dir=str(tmp_path), max_native_bytes_per_session=2)
    )

    response = client.post(
        "/v1/native/sessions/native-s1/windows",
        json={"start_ms": 0, "end_ms": 1000, "video_mp4_base64": mp4_b64(b"abc"), "mime_type": "video/mp4"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "decoded video bytes exceed max_window_bytes"
