import base64

from local_infer.frame_store import FrameStore
from local_infer.payloads import build_chat_messages


def b64(s: str) -> str:
    return base64.b64encode(s.encode()).decode()


def test_frame_store_keeps_only_max_frames_and_returns_recent_in_order():
    store = FrameStore(max_frames_per_session=3)

    for i in range(5):
        store.add_frame("s1", timestamp_ms=i * 1000, frame_jpeg_base64=b64(f"frame-{i}"))

    recent = store.get_recent_frames("s1", limit=3)

    assert [f.timestamp_ms for f in recent] == [2000, 3000, 4000]
    assert [base64.b64decode(f.frame_jpeg_base64).decode() for f in recent] == [
        "frame-2",
        "frame-3",
        "frame-4",
    ]


def test_build_chat_messages_uses_multiple_image_urls_before_text_prompt():
    store = FrameStore(max_frames_per_session=10)
    store.add_frame("interview-1", 1000, b64("jpeg-a"))
    store.add_frame("interview-1", 2000, b64("jpeg-b"))

    messages = build_chat_messages(
        frames=store.get_recent_frames("interview-1", limit=2),
        prompt="지원자의 현재 상태를 짧게 말해줘.",
        system_prompt="한국어 면접관으로 답하세요.",
    )

    assert messages[0] == {"role": "system", "content": "한국어 면접관으로 답하세요."}
    assert messages[1]["role"] == "user"
    assert messages[1]["content"][-1] == {"type": "text", "text": "지원자의 현재 상태를 짧게 말해줘."}
    image_parts = messages[1]["content"][:-1]
    assert [part["type"] for part in image_parts] == ["image_url", "image_url"]
    assert image_parts[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert image_parts[0]["image_url"]["url"].endswith(b64("jpeg-a"))
    assert image_parts[1]["image_url"]["url"].endswith(b64("jpeg-b"))
