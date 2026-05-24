# pyright: reportMissingImports=false
from pathlib import Path
from typing import Any

import pytest

import local_infer.native_payloads as native_payloads
from local_infer.native_audio import NativeInputAudio
from local_infer.native_payloads import (
    DEFAULT_NATIVE_SYSTEM_PROMPT,
    build_native_chat_messages,
    build_native_chat_payload,
    summarize_native_payload,
)


def test_build_native_chat_messages_uses_video_audio_text_order_and_shape():
    audio = NativeInputAudio(data="UklGRndhdg==")

    messages = build_native_chat_messages(
        video_file_url="file:///native-media/interview/window.mp4",
        input_audio=audio,
        prompt="지원자의 답변을 짧게 평가하고 후속 질문을 해줘.",
        system_prompt="한국어 면접관으로 답하세요.",
    )

    assert messages[0] == {"role": "system", "content": "한국어 면접관으로 답하세요."}
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == [
        {
            "type": "video_url",
            "video_url": {"url": "file:///native-media/interview/window.mp4"},
        },
        {
            "type": "input_audio",
            "input_audio": {"data": "UklGRndhdg==", "format": "wav"},
        },
        {"type": "text", "text": "지원자의 답변을 짧게 평가하고 후속 질문을 해줘."},
    ]


def test_build_native_chat_messages_uses_default_korean_interview_system_prompt():
    messages = build_native_chat_messages(
        video_file_url="file:///native-media/interview/window.mp4",
        input_audio=NativeInputAudio(data="audio"),
        prompt="후속 질문 하나만 해줘.",
    )

    assert messages[0] == {"role": "system", "content": DEFAULT_NATIVE_SYSTEM_PROMPT}
    assert "한국어" in DEFAULT_NATIVE_SYSTEM_PROMPT
    assert "면접관" in DEFAULT_NATIVE_SYSTEM_PROMPT


def test_build_native_chat_payload_includes_model_generation_fields_and_stream_true():
    payload = build_native_chat_payload(
        model="google/gemma-4-31b-it",
        video_file_url="file:///native-media/interview/window.mp4",
        input_audio=NativeInputAudio(data="audio"),
        prompt="질문",
        max_tokens=64,
        temperature=0.15,
        stream=True,
    )

    assert payload["model"] == "google/gemma-4-31b-it"
    assert payload["max_tokens"] == 64
    assert payload["temperature"] == 0.15
    assert payload["stream"] is True
    assert payload["messages"][1]["content"][0]["type"] == "video_url"
    assert payload["messages"][1]["content"][1]["type"] == "input_audio"
    assert payload["messages"][1]["content"][2] == {"type": "text", "text": "질문"}


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"video_file_url": ""}, "video_file_url must be non-empty"),
        ({"input_audio": None}, "input_audio is required"),
        ({"input_audio": NativeInputAudio(data="audio", format="mp3")}, "input_audio format must be wav"),
        ({"prompt": ""}, "prompt must be non-empty"),
    ],
)
def test_build_native_chat_messages_rejects_invalid_inputs(kwargs, message):
    defaults: dict[str, Any] = {
        "video_file_url": "file:///native-media/interview/window.mp4",
        "input_audio": NativeInputAudio(data="audio"),
        "prompt": "질문",
    }
    defaults.update(kwargs)

    with pytest.raises(ValueError, match=message):
        build_native_chat_messages(**defaults)


def test_forbidden_native_payload_output_has_no_frame_fallback_transcript_or_analysis_markers():
    payload = build_native_chat_payload(
        model="native-model",
        video_file_url="file:///native-media/interview/window.mp4",
        input_audio=NativeInputAudio(data="audio"),
        prompt="질문",
    )

    payload_text = repr(payload).lower()
    forbidden_terms = [
        "image_url",
        "audio_analysis",
        "fallback",
        "transcript",
        "ground_truth",
        "asr",
        "vad",
        "/audio",
        "/generate-av-fallback",
    ]
    assert [term for term in forbidden_terms if term in payload_text] == []

    summary = summarize_native_payload(payload)
    assert summary["video_url_present"] is True
    assert summary["input_audio_present"] is True
    assert summary["image_url_present"] is False
    assert summary["fallback_used"] is False
    assert summary["video_url_count"] == 1
    assert summary["input_audio_count"] == 1
    assert summary["text_count"] == 1


def test_forbidden_native_payloads_module_does_not_import_frame_or_frame_payload_builder():
    assert native_payloads.__file__ is not None
    source = Path(native_payloads.__file__).read_text()

    forbidden_terms = [
        "from .frame_store import Frame",
        "from local_infer.frame_store import Frame",
        "build_chat_payload",
        "audio_analysis",
        "transcript",
    ]
    assert [term for term in forbidden_terms if term in source] == []
