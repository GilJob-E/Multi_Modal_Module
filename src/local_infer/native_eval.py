"""턴 단위 native AV 면접 평가자 + periodic prefill.

검증된 레시피(Phase 1 스파이크): 샘플 image_url 프레임 + audio_url을 E4B에 한 번에
보내 verbal/vocal/visual 종합 평가를 받는다. 평가 루브릭은 system 프롬프트에 고정하고
user 턴은 [프레임…, audio, 고정 text]만 둔다 → warm 요청과 evaluate 요청이 전체
prefix를 공유해 vLLM prefix 캐시가 풀히트한다(스파이크 warm TTFT 0.03s 재현).
warm/evaluate는 같은 프레임·오디오 객체를 써야 토큰이 일치해 캐시가 맞는다.
"""
from __future__ import annotations

from collections.abc import Iterator

from .frame_store import Frame, FrameStore
from .native_audio import NativeInputAudio
from .vllm_client import VllmClient, default_vllm_client

MODEL = "google/gemma-4-E4B-it"

DEFAULT_EVAL_SYSTEM_PROMPT = (
    "당신은 화상 면접관입니다. 제시되는 지원자 답변(프레임 이미지 + 음성)을 "
    "아래 세 축으로 종합 평가하세요.\n"
    "1) 언어(verbal): 답변 내용의 논리·구조·구체성.\n"
    "2) 청각(vocal): 전달력 — 특히 음량 변화, 말 속도, pause(머뭇거림/공백), "
    "억양이 단조로운지 풍부한지 구체적으로 짚어주세요.\n"
    "3) 시각(visual): 표정·시선·자세 등 비언어 단서.\n"
    "각 축마다 관찰한 근거와 개선점을 함께 적으세요."
)

# 고정 user 지시 — system 루브릭과 함께 warm/evaluate 양쪽에서 동일하게 쓰여 prefix를 보존한다.
EVAL_USER_TEXT = "위 답변을 평가하세요."


def _frame_part(frame: Frame) -> dict:
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{frame.frame_jpeg_base64}"}}


def build_av_messages(*, system_prompt: str, frames: list[Frame], audio: NativeInputAudio) -> list[dict]:
    content: list[dict] = [_frame_part(f) for f in frames]
    content.append(audio.to_content_part())
    content.append({"type": "text", "text": EVAL_USER_TEXT})
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content},
    ]


class NativeInterviewEvaluator:
    """vLLM을 숨긴 단일 인터페이스. 턴 동안 프레임/오디오를 받고(add_frame/set_audio_window),
    push마다 warm()으로 prefix를 캐시에 태운 뒤, end-of-turn에 evaluate()로 평가를 스트리밍한다.
    """

    def __init__(
        self,
        *,
        client: VllmClient | None = None,
        model: str = MODEL,
        system_prompt: str = DEFAULT_EVAL_SYSTEM_PROMPT,
        frame_store: FrameStore | None = None,
    ) -> None:
        self.client = client or default_vllm_client()
        self.model = model
        self.system_prompt = system_prompt
        self.frames = frame_store or FrameStore()
        self._audio: dict[str, NativeInputAudio] = {}

    def add_frame(self, session_id: str, timestamp_ms: int, frame_jpeg_base64: str) -> None:
        self.frames.add_frame(session_id, timestamp_ms, frame_jpeg_base64)

    def set_audio_window(self, session_id: str, audio: NativeInputAudio) -> None:
        self._audio[session_id] = audio

    def _payload(self, session_id: str, *, n_frames: int, max_tokens: int) -> dict:
        audio = self._audio.get(session_id)
        if audio is None:
            raise ValueError(f"no audio window set for session {session_id!r}")
        frames = self.frames.get_recent_frames(session_id, n_frames)
        if not frames:
            raise ValueError(f"no frames stored for session {session_id!r}")
        return {
            "model": self.model,
            "messages": build_av_messages(system_prompt=self.system_prompt, frames=frames, audio=audio),
            "max_tokens": max_tokens,
            "temperature": 0.0,
            "stream": True,
        }

    def warm(self, session_id: str, *, n_frames: int = 3) -> None:
        """현재 prefix를 vLLM prefix 캐시에 태운다(max_tokens=1, 출력 폐기)."""
        for _ in self.client.stream_chat(self._payload(session_id, n_frames=n_frames, max_tokens=1)):
            pass

    def evaluate(self, session_id: str, *, n_frames: int = 3, max_tokens: int = 768) -> Iterator[str]:
        """평가를 토큰 단위로 스트리밍한다. 호출자가 TTFT를 측정한다."""
        yield from self.client.stream_chat(self._payload(session_id, n_frames=n_frames, max_tokens=max_tokens))
