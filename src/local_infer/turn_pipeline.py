"""슬라이딩 윈도우 턴 파이프라인 — 발화 중 윈도우 독립 추론, end-of-turn은 마지막 윈도우만.

GilJob이 1fps 프레임 + 16kHz PCM을 흘려보내면, 이 파이프라인이:
  - 채널 ①: ~3초마다 비언어 read (저지연)
  - 채널 ②: ~16초마다 평가 윈도우
each window = **독립 추론**(KV prefix-stability 불필요, D8). 신호는 발생 즉시 on_signal로 emit.
**집계 없음** — per-window 신호만 내보내고 종합은 Gemini 몫(end_turn도 마지막 윈도우만 처리).

라이브 사용: add_frame/add_audio로 도착분을 넣고, poll(now)로 그 시점까지 due한 윈도우를
독립 추론해 emit, 발화 종료 시 end_turn(now)으로 남은 tail을 flush.
evaluator는 read_nonverbal/evaluate_window 두 메서드만 있으면 됨(WindowEvaluator 또는 fake).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from .signals import EvaluationSignal, NonVerbalSignal


class _Evaluator(Protocol):
    def read_nonverbal(
        self, jpeg_frames: list[bytes], pcm: bytes, *, t: float, window_s: float,
        src_fps: float = ..., sample_rate: int = ...,
    ) -> NonVerbalSignal: ...

    def evaluate_window(
        self, jpeg_frames: list[bytes], pcm: bytes, *, window_start_s: float, window_dur_s: float,
        src_fps: float = ..., sample_rate: int = ...,
    ) -> EvaluationSignal: ...


class SlidingWindowPipeline:
    def __init__(
        self,
        evaluator: _Evaluator,
        *,
        on_signal: Callable[[NonVerbalSignal | EvaluationSignal], None],
        nonverbal_window_s: float = 3.0,
        eval_window_s: float = 16.0,
        src_fps: float = 1.0,
        sample_rate: int = 16000,
    ) -> None:
        self.ev = evaluator
        self.on_signal = on_signal
        self.nv_w = nonverbal_window_s
        self.eval_w = eval_window_s
        self.src_fps = src_fps
        self.sample_rate = sample_rate
        self._frames: list[tuple[float, bytes]] = []
        self._audio: list[tuple[float, bytes]] = []
        self._next_nv_end = nonverbal_window_s
        self._next_eval_end = eval_window_s

    def add_frame(self, t_s: float, jpeg: bytes) -> None:
        self._frames.append((t_s, jpeg))

    def add_audio(self, t_s: float, pcm: bytes) -> None:
        self._audio.append((t_s, pcm))

    def _slice(self, start_s: float, end_s: float) -> tuple[list[bytes], bytes]:
        frames = [j for (t, j) in self._frames if start_s <= t < end_s]
        pcm = b"".join(p for (t, p) in self._audio if start_s <= t < end_s)
        return frames, pcm

    def _emit(self, sig: NonVerbalSignal | EvaluationSignal) -> None:
        self.on_signal(sig)

    def _run_nonverbal(self, start_s: float, dur_s: float) -> None:
        frames, pcm = self._slice(start_s, start_s + dur_s)
        if not frames:
            return  # 비디오 없는 구간은 비언어 read 스킵
        self._emit(self.ev.read_nonverbal(
            frames, pcm, t=start_s + dur_s / 2, window_s=dur_s,
            src_fps=self.src_fps, sample_rate=self.sample_rate,
        ))

    def _run_eval(self, start_s: float, dur_s: float) -> None:
        frames, pcm = self._slice(start_s, start_s + dur_s)
        if not frames or not pcm:
            return  # 평가는 영상+오디오 둘 다 필요
        self._emit(self.ev.evaluate_window(
            frames, pcm, window_start_s=start_s, window_dur_s=dur_s,
            src_fps=self.src_fps, sample_rate=self.sample_rate,
        ))

    def poll(self, now_s: float) -> None:
        """now_s 시점까지 완성된 윈도우들을 독립 추론해 emit."""
        while self._next_nv_end <= now_s:
            self._run_nonverbal(self._next_nv_end - self.nv_w, self.nv_w)
            self._next_nv_end += self.nv_w
        while self._next_eval_end <= now_s:
            self._run_eval(self._next_eval_end - self.eval_w, self.eval_w)
            self._next_eval_end += self.eval_w

    def end_turn(self, now_s: float) -> None:
        """발화 종료: 아직 안 낸 tail을 마지막 윈도우로 처리(집계 없음)."""
        self.poll(now_s)
        # 비언어 tail: 마지막 완성 윈도우 끝~now
        nv_tail_start = self._next_nv_end - self.nv_w
        if now_s - nv_tail_start > 0.5:  # 0.5s 미만 자투리는 무시
            self._run_nonverbal(nv_tail_start, now_s - nv_tail_start)
        # 평가 tail: 마지막 완성 평가 윈도우 끝~now (남은 답변 끝부분)
        eval_tail_start = self._next_eval_end - self.eval_w
        if now_s - eval_tail_start > 1.0:
            self._run_eval(eval_tail_start, now_s - eval_tail_start)
