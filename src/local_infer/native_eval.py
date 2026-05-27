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


# ─── M2: 윈도우 평가자 (D8 video_url+audio_url 경로, per-window 구조화 신호) ─────────────
# 위 NativeInterviewEvaluator는 Phase 3의 image_url+periodic-prefill 경로(D8로 대체).
# 아래가 제품 경로: 윈도우(1fps 프레임+PCM) → video_url+audio_url → E4B → JSON 신호.

import json
import re

from .signals import NONVERBAL_STATES, EvaluationSignal, NonVerbalSignal
from .window_assembly import assemble_audio_url, assemble_video_url

NONVERBAL_SYSTEM = (
    "You are observing a job candidate during a live video interview — a few seconds of "
    "video (with audio). Read ONLY their non-verbal state right now from face, eyes, posture, "
    "and voice tone. Do NOT transcribe or judge answer content. Respond with a SINGLE JSON "
    "object and nothing else: "
    '{"state": one of ' + "[" + ", ".join(NONVERBAL_STATES) + "], "
    '"intensity": number 0.0-1.0, "note": short phrase}.'
)

EVAL_SYSTEM = (
    "당신은 까다롭고 안목 높은 면접관입니다. 지원자 답변의 ~16초 구간을 멀티모달(영상+음성)로 "
    "**비평**하세요. 칭찬을 나열하는 평가자가 아니라 *비평가*로서, 각 축마다 잘한 점이 있으면 "
    "짚되 **약점·어색함·우려·개선점을 반드시 구체적으로 지적**하세요. 무난하거나 부족하거나 "
    "평범하면 솔직히 그렇게 쓰세요. '안정적', '자연스러움' 같은 일반론적 호평으로 때우지 마세요. "
    "오직 SINGLE JSON object로만 답하세요(키): "
    '"verbal": {"logic": str, "structure": str, "specificity": str}, '
    '"vocal": {"volume": str, "pace": str, "pauses": str, "intonation": str}, '
    '"visual": {"eye_contact": str, "posture": str, "expression": str, "gesture_over_time": str}, '
    '"critique": [str, ...]  // 면접관으로서 이 구간에서 가장 걸리는 약점·우려 1~3개(필수, 비워두지 말 것), '
    '"key_observations": [str, ...]. 각 leaf는 한국어 짧은 비평.'
)


def _video_part(url: str) -> dict:
    return {"type": "video_url", "video_url": {"url": url}}


def _audio_part(url: str) -> dict:
    return {"type": "audio_url", "audio_url": {"url": url}}


def _extract_json(text: str) -> dict:
    """모델 출력에서 첫 JSON object를 파싱. 실패 시 ValueError."""
    text = text.strip()
    # ```json ... ``` 펜스 제거
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if m:
        return json.loads(m.group(0))
    raise ValueError(f"no JSON object in output: {text[:200]!r}")


class WindowEvaluator:
    """vLLM을 숨긴 윈도우 단위 평가자. 윈도우(1fps JPEG 프레임 + 16kHz PCM)를 받아
    video_url+audio_url로 조립해 E4B에 보내고, per-window 구조화 신호를 반환한다.
    집계는 하지 않는다(Gemini 몫) — 두 메서드 모두 *한 윈도우*의 신호만 낸다.
    """

    def __init__(self, *, client: VllmClient | None = None, model: str = MODEL) -> None:
        self.client = client or default_vllm_client()
        self.model = model

    def _ask_json(self, *, system: str, content: list[dict], max_tokens: int) -> dict:
        resp = self.client.chat(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": content},
                ],
                "max_tokens": max_tokens,
                "temperature": 0.0,
            }
        )
        return _extract_json(resp["choices"][0]["message"]["content"])

    def read_nonverbal(
        self,
        jpeg_frames: list[bytes],
        pcm: bytes,
        *,
        t: float,
        window_s: float,
        src_fps: float = 1.0,
        sample_rate: int = 16000,
    ) -> NonVerbalSignal:
        """채널 ① — 짧은 윈도우에서 지원자 비언어 상태 read."""
        content = [_video_part(assemble_video_url(jpeg_frames, src_fps=src_fps))]
        if pcm:
            content.append(_audio_part(assemble_audio_url(pcm, sample_rate=sample_rate)))
        content.append({"type": "text", "text": "Read the candidate's non-verbal state now."})
        data = self._ask_json(system=NONVERBAL_SYSTEM, content=content, max_tokens=96)
        state = str(data.get("state", "neutral")).strip().lower()
        if state not in NONVERBAL_STATES:
            state = "neutral"
        try:
            intensity = max(0.0, min(1.0, float(data.get("intensity", 0.0))))
        except (TypeError, ValueError):
            intensity = 0.0
        return NonVerbalSignal(
            t=t, window_s=window_s, state=state, intensity=intensity,
            note=str(data.get("note", ""))[:120],
        )

    def evaluate_window(
        self,
        jpeg_frames: list[bytes],
        pcm: bytes,
        *,
        window_start_s: float,
        window_dur_s: float,
        src_fps: float = 1.0,
        sample_rate: int = 16000,
    ) -> EvaluationSignal:
        """채널 ② — 16초 윈도우 verbal/vocal/visual 평가."""
        content = [
            _video_part(assemble_video_url(jpeg_frames, src_fps=src_fps)),
            _audio_part(assemble_audio_url(pcm, sample_rate=sample_rate)),
            {"type": "text", "text": "Evaluate this answer window."},
        ]
        data = self._ask_json(system=EVAL_SYSTEM, content=content, max_tokens=640)
        return EvaluationSignal(
            window_start_s=window_start_s,
            window_dur_s=window_dur_s,
            verbal=data.get("verbal", {}) if isinstance(data.get("verbal"), dict) else {},
            vocal=data.get("vocal", {}) if isinstance(data.get("vocal"), dict) else {},
            visual=data.get("visual", {}) if isinstance(data.get("visual"), dict) else {},
            critique=[str(x) for x in data.get("critique", [])][:5],
            key_observations=[str(x) for x in data.get("key_observations", [])][:8],
        )
