from __future__ import annotations

from .frame_store import Frame

DEFAULT_SYSTEM_PROMPT = (
    "당신은 한국어 화상 면접관입니다. 지원자의 영상 프레임이 1초 간격으로 전달됩니다. "
    "표정·자세의 변화를 관찰하되, 답변은 짧고 자연스럽게 한 번에 한 질문만 하세요."
)


def build_chat_messages(
    *,
    frames: list[Frame],
    prompt: str,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
) -> list[dict]:
    """Build OpenAI-compatible multimodal chat messages for vLLM.

    Frames are sent as multiple `image_url` parts before the text prompt. This
    matches the Phase 0 latency result: cumulative image frames are the module
    interface; full `video_url` clips are not on the critical path.
    """
    content = [
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{frame.frame_jpeg_base64}"},
        }
        for frame in frames
    ]
    content.append({"type": "text", "text": prompt})
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content},
    ]


def build_chat_payload(
    *,
    model: str,
    frames: list[Frame],
    prompt: str,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    max_tokens: int = 128,
    temperature: float = 0.2,
    stream: bool = True,
) -> dict:
    return {
        "model": model,
        "stream": stream,
        "messages": build_chat_messages(
            frames=frames,
            prompt=prompt,
            system_prompt=system_prompt,
        ),
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
