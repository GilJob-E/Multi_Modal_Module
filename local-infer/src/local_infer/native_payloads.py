from __future__ import annotations

# pyright: reportMissingImports=false

from typing import Any

from .native_audio import NativeInputAudio

DEFAULT_NATIVE_SYSTEM_PROMPT = (
    "당신은 한국어 화상 면접관입니다. 지원자의 영상과 음성을 함께 보고 "
    "짧고 자연스럽게 한 번에 하나의 후속 질문만 하세요."
)


def build_native_chat_messages(
    *,
    video_file_url: str,
    input_audio: NativeInputAudio,
    prompt: str,
    system_prompt: str = DEFAULT_NATIVE_SYSTEM_PROMPT,
) -> list[dict[str, Any]]:
    _validate_native_inputs(video_file_url=video_file_url, input_audio=input_audio, prompt=prompt)

    content = [
        {"type": "video_url", "video_url": {"url": video_file_url}},
        input_audio.to_content_part(),
        {"type": "text", "text": prompt},
    ]
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content},
    ]


def build_native_chat_payload(
    *,
    model: str,
    video_file_url: str,
    input_audio: NativeInputAudio,
    prompt: str,
    system_prompt: str = DEFAULT_NATIVE_SYSTEM_PROMPT,
    max_tokens: int = 128,
    temperature: float = 0.2,
    stream: bool = True,
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": build_native_chat_messages(
            video_file_url=video_file_url,
            input_audio=input_audio,
            prompt=prompt,
            system_prompt=system_prompt,
        ),
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": stream,
    }


def summarize_native_payload(payload: dict[str, Any]) -> dict[str, Any]:
    parts = _user_content_parts(payload)
    types = [part.get("type") for part in parts if isinstance(part, dict)]
    payload_text = repr(payload).lower()
    return {
        "message_count": len(payload.get("messages", [])) if isinstance(payload.get("messages"), list) else 0,
        "content_part_count": len(parts),
        "video_url_count": types.count("video_url"),
        "input_audio_count": types.count("input_audio"),
        "text_count": types.count("text"),
        "video_url_present": "video_url" in types,
        "input_audio_present": "input_audio" in types,
        "image_url_present": "image_url" in types,
        "fallback_used": "fallback" in payload_text,
    }


def _validate_native_inputs(*, video_file_url: str, input_audio: NativeInputAudio, prompt: str) -> None:
    if not video_file_url:
        raise ValueError("video_file_url must be non-empty")
    if input_audio is None:
        raise ValueError("input_audio is required")
    if input_audio.format != "wav":
        raise ValueError("input_audio format must be wav")
    if not prompt:
        raise ValueError("prompt must be non-empty")


def _user_content_parts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    messages = payload.get("messages", [])
    if not isinstance(messages, list):
        return []
    for message in messages:
        if isinstance(message, dict) and message.get("role") == "user" and isinstance(message.get("content"), list):
            return message["content"]
    return []
