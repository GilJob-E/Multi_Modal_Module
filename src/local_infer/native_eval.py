"""윈도우 단위 native AV 면접 분석자 (D8 video_url+audio_url 경로).

윈도우(1fps JPEG 프레임 + 16kHz PCM)를 video_url+audio_url로 조립해 E4B에 보내고,
per-window 구조화 신호를 낸다 — 채널① 비언어 read, 채널② verbal/vocal/visual 비평.
집계는 하지 않는다(Gemini 몫). vLLM은 이 평가자 뒤에 숨는다.
"""
from __future__ import annotations

import json
import re

from .signals import NONVERBAL_STATES, EvaluationSignal, NonVerbalSignal
from .vllm_client import VllmClient, default_vllm_client
from .window_assembly import assemble_audio_url, assemble_video_url

MODEL = "google/gemma-4-E4B-it"

NONVERBAL_SYSTEM = (
    "당신은 지원자의 비언어 신호를 예리하게 읽는 면접관입니다. 지금 이 짧은 구간(몇 초)의 "
    "영상+음성에서 지원자의 상태를 *있는 그대로* 판별하세요. 답변 내용·논리는 보지 말고 "
    "비언어(표정, 시선, 자세, 목소리 톤·떨림)만. "
    "중요: 무난해 보여도 안전하게 'engaged'로 때우지 마세요. 시선 이탈·깜빡임, 경직되거나 "
    "무너지는 자세, 망설임·말 끊김, 긴장·불안, 에너지/자신감의 *변화*를 적극적으로 포착해 "
    "구분하세요. intensity는 신호의 실제 강도를 눈금에 맞게 매기세요 — 습관적으로 0.8을 찍지 "
    "말 것. 약하거나 애매하면 0.2~0.4, 중간이면 0.5, 뚜렷할 때만 0.7+. "
    "오직 SINGLE JSON object로만 답하세요: "
    '{"state": one of ' + "[" + ", ".join(NONVERBAL_STATES) + "], "
    '"intensity": number 0.0-1.0, "note": 관찰한 구체 단서(한국어 짧게)}.'
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
        """채널 ② — 16초 윈도우 verbal/vocal/visual 비평."""
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
