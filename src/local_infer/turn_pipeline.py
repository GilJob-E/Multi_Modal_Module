"""슬라이딩 윈도우 턴 파이프라인 — 발화 중 윈도우 독립 추론(백그라운드), end-of-turn은 compact tail만.

GilJob이 1fps 프레임 + 16kHz PCM을 흘려보내면, 이 파이프라인이:
  - 채널 ①: ~3초마다 비언어 read (저지연)
  - 채널 ②: ~16초마다 평가 윈도우 (풀 비평)
each window = **독립 추론**(KV prefix-stability 불필요, D8).

**추론은 백그라운드 실행**(executor)된다 — poll/add_*는 즉시 반환하고 추론은 워커 스레드에서
돈다. **세 실행 레인**을 분리해 서로 막지 않게 한다:
  - 빠른 레인(_nv_exec): 비언어 read(채널①)
  - 느린 레인(_eval_exec): 발화 중 풀 평가(채널②, ~7s)
  - tail 레인(_tail_exec, 워커 1): end-of-turn compact tail 전용 → 비언어/풀 평가에 안 밀림.
counter는 *제출 시점*에 전진하므로 동시 poll에도 같은 윈도우를 두 번 추론하지 않는다
(race-free, lock 보호). 워커 예외는 삼키지 않고 로깅한다(silent drop 방지).

**집계 없음** — per-window 신호만 내보내고 종합은 Gemini 몫. **신호는 완료 순으로 emit되므로
시간순이 아닐 수 있다 — 소비자는 타임스탬프(t / window_start_s)로 정렬**(자기기술적). end_turn은
답변 *마지막 구간*만 **compact 평가**(짧은 출력 → turn 종료 지연 ≤목표, 체감 레이턴시)하고,
발화 중 완성된 풀 윈도우는 이미 emit돼 있어 그것들을 기다리지 않는다. end_turn 시점에 아직 도는
풀 평가는 **의도적으로 버린다**(그 구간 내용은 compact tail이 다시 커버) — close() 후의 emit은
no-op(_closed 가드)이라 안전.

라이브 사용: add_frame/add_audio로 도착분을 넣고, poll(now)로 그 시점까지 due한 윈도우를
백그라운드 제출, drain()으로 완료된 신호를 수거, 발화 종료 시 end_turn(now)으로 compact tail flush.
evaluator는 read_nonverbal/evaluate_window 두 메서드만 있으면 됨(WindowEvaluator 또는 fake).
테스트는 executor=InlineExecutor()를 주입해 동기·결정적으로 검증한다(동시성은 실 스레드풀 테스트로).
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, wait
from typing import Protocol

from .signals import EvaluationSignal, NonVerbalSignal

logger = logging.getLogger(__name__)


class _Evaluator(Protocol):
    def read_nonverbal(
        self, jpeg_frames: list[bytes], pcm: bytes, *, t: float, window_s: float,
        src_fps: float = ..., sample_rate: int = ...,
    ) -> NonVerbalSignal: ...

    def evaluate_window(
        self, jpeg_frames: list[bytes], pcm: bytes, *, window_start_s: float, window_dur_s: float,
        src_fps: float = ..., sample_rate: int = ..., compact: bool = ...,
    ) -> EvaluationSignal: ...


class InlineExecutor:
    """submit이 함수를 즉시 동기 실행 — 테스트/결정성용 (futures는 완료 상태로 반환).

    프로덕션 기본은 스레드풀(백그라운드)이지만, 테스트는 이걸 주입해 추론이 호출 즉시 끝나게 해
    윈도우 스케줄·집계 없음·compact tail 로직을 GPU/타이밍 없이 결정적으로 검증한다.
    (실제 동시성·레인 독립성은 별도의 실-스레드풀 테스트로 검증.)
    """

    def submit(self, fn: Callable[..., object], *args, **kwargs) -> Future:
        fut: Future = Future()
        try:
            fut.set_result(fn(*args, **kwargs))
        except BaseException as exc:  # noqa: BLE001 - 워커 예외를 future로 전달(스레드풀과 동형)
            fut.set_exception(exc)
        return fut

    def shutdown(self, wait: bool = True) -> None:  # noqa: A002, FBT001, FBT002
        pass


class SlidingWindowPipeline:
    def __init__(
        self,
        evaluator: _Evaluator,
        *,
        on_signal: Callable[[NonVerbalSignal | EvaluationSignal], None] | None = None,
        nonverbal_window_s: float = 3.0,
        eval_window_s: float = 16.0,
        src_fps: float = 1.0,
        sample_rate: int = 16000,
        executor=None,
        nv_executor=None,
        eval_executor=None,
        tail_executor=None,
        eot_deadline_s: float = 3.0,
    ) -> None:
        self.ev = evaluator
        self.on_signal = on_signal
        self.nv_w = nonverbal_window_s
        self.eval_w = eval_window_s
        self.src_fps = src_fps
        self.sample_rate = sample_rate
        self.eot_deadline_s = eot_deadline_s  # compact tail을 기다리는 안전 상한(backstop)

        # 실행 레인. executor 주입 시 세 레인 공용(InlineExecutor=동기, 테스트용).
        # nv/eval/tail executor를 따로 주입하면 그걸 쓰고(앱-레벨 공유), 다 None이면 자체 생성.
        if executor is not None:
            nv_executor = eval_executor = tail_executor = executor
        self._owns_exec = nv_executor is None
        if self._owns_exec:
            self._nv_exec = ThreadPoolExecutor(max_workers=2, thread_name_prefix="gje-nv")
            self._eval_exec = ThreadPoolExecutor(max_workers=2, thread_name_prefix="gje-eval")
            self._tail_exec = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gje-tail")
        else:
            self._nv_exec, self._eval_exec, self._tail_exec = nv_executor, eval_executor, tail_executor

        self._lock = threading.Lock()       # 입력 버퍼 + 스케줄 counter + covered_until 보호
        self._out_lock = threading.Lock()   # 출력 버퍼 + _closed 보호
        self._fut_lock = threading.Lock()   # 추적 future 리스트 보호
        self._frames: list[tuple[float, bytes]] = []
        self._audio: list[tuple[float, bytes]] = []
        self._next_nv_end = nonverbal_window_s
        self._next_eval_end = eval_window_s
        self._eval_covered_until = 0.0      # 풀 평가가 *연속 성공* 완료된 끝 시각 → eot compact tail 시작점
        self._eval_done_ends: set[float] = set()  # 성공한 풀 윈도우 end(그리드) — 연속 prefix 계산용
        self._out: list[NonVerbalSignal | EvaluationSignal] = []
        self._futures: list[Future] = []
        self._closed = False

    # ── 입력 ──
    def add_frame(self, t_s: float, jpeg: bytes) -> None:
        with self._lock:
            self._frames.append((t_s, jpeg))

    def add_audio(self, t_s: float, pcm: bytes) -> None:
        with self._lock:
            self._audio.append((t_s, pcm))

    def _slice(self, start_s: float, end_s: float) -> tuple[list[bytes], bytes]:
        # 호출자가 self._lock을 잡은 상태에서 호출(버퍼 일관성 — append와 경합 방지).
        frames = [j for (t, j) in self._frames if start_s <= t < end_s]
        pcm = b"".join(p for (t, p) in self._audio if start_s <= t < end_s)
        return frames, pcm

    # ── 출력 ──
    def _emit(self, sig: NonVerbalSignal | EvaluationSignal) -> None:
        with self._out_lock:
            if self._closed:  # close() 후 도착한 in-flight 신호는 버린다(orphaned append 방지)
                return
            self._out.append(sig)
        if self.on_signal is not None:
            self.on_signal(sig)

    def drain(self) -> list[NonVerbalSignal | EvaluationSignal]:
        """지금까지 완료돼 모인 신호를 꺼내고 버퍼를 비운다(스레드 안전, point-in-time 스냅샷)."""
        with self._out_lock:
            out = self._out
            self._out = []
        return out

    # ── 추적/대기 ──
    def _submit(self, executor, fn: Callable[..., object], *args) -> Future:
        fut = executor.submit(fn, *args)
        with self._fut_lock:
            self._futures = [f for f in self._futures if not f.done()]
            self._futures.append(fut)
        return fut

    def wait_idle(self, timeout: float | None = None) -> None:
        """제출된 모든 백그라운드 추론이 끝날 때까지 대기(테스트/종료 정리용)."""
        with self._fut_lock:
            pending = [f for f in self._futures if not f.done()]
        if pending:
            wait(pending, timeout=timeout)

    # ── 워커 잡 (예외는 로깅하고 삼킨다 — 한 윈도우 실패가 파이프라인을 죽이지 않게) ──
    def _do_nv(self, start_s: float, dur_s: float, frames: list[bytes], pcm: bytes):
        try:
            sig = self.ev.read_nonverbal(
                frames, pcm, t=start_s + dur_s / 2, window_s=dur_s,
                src_fps=self.src_fps, sample_rate=self.sample_rate,
            )
        except Exception:  # noqa: BLE001 - 워커 실패는 로깅하고 신호만 누락(다음 read가 커버)
            logger.exception("nonverbal read failed [%.1f, +%.1fs]", start_s, dur_s)
            return None
        self._emit(sig)
        return sig

    def _do_eval(self, start_s: float, dur_s: float, frames: list[bytes], pcm: bytes, compact: bool):
        try:
            sig = self.ev.evaluate_window(
                frames, pcm, window_start_s=start_s, window_dur_s=dur_s,
                src_fps=self.src_fps, sample_rate=self.sample_rate, compact=compact,
            )
        except Exception:  # noqa: BLE001 - 실패 시 covered_until 전진 안 함 → eot compact tail이 재커버
            logger.exception("eval failed [%.1f, +%.1fs] compact=%s", start_s, dur_s, compact)
            return None
        if not compact:  # 풀 윈도우 성공 → *연속 성공* prefix만큼 covered_until 전진.
            # max()가 아니라 연속 prefix라야: 앞 윈도우가 실패/지연되면 covered_until이 그 구멍을
            # 건너뛰지 않고 멈춘다 → 그 미평가 구간을 end_turn compact tail이 다시 커버(누락 방지).
            with self._lock:
                self._eval_done_ends.add(start_s + dur_s)
                nxt = self._eval_covered_until + self.eval_w
                while nxt in self._eval_done_ends:
                    self._eval_covered_until = nxt
                    nxt += self.eval_w
        self._emit(sig)
        return sig

    # ── 스케줄 ──
    def poll(self, now_s: float) -> None:
        """now_s까지 완성된 윈도우들을 백그라운드 추론에 제출(즉시 반환, race-free)."""
        nv_jobs: list[tuple[float, float, list[bytes], bytes]] = []
        eval_jobs: list[tuple[float, float, list[bytes], bytes]] = []
        with self._lock:
            while self._next_nv_end <= now_s:
                start = self._next_nv_end - self.nv_w
                self._next_nv_end += self.nv_w  # 제출 *전에* 전진 → 동시 poll 중복 방지
                frames, pcm = self._slice(start, start + self.nv_w)
                nv_jobs.append((start, self.nv_w, frames, pcm))
            while self._next_eval_end <= now_s:
                start = self._next_eval_end - self.eval_w
                self._next_eval_end += self.eval_w
                frames, pcm = self._slice(start, start + self.eval_w)
                eval_jobs.append((start, self.eval_w, frames, pcm))
        for (start, dur, frames, pcm) in nv_jobs:
            if frames:  # 비디오 없는 구간은 비언어 read 스킵
                self._submit(self._nv_exec, self._do_nv, start, dur, frames, pcm)
        for (start, dur, frames, pcm) in eval_jobs:
            if frames and pcm:  # 평가는 영상+오디오 둘 다 필요
                self._submit(self._eval_exec, self._do_eval, start, dur, frames, pcm, False)

    def end_turn(self, now_s: float) -> None:
        """발화 종료: 답변 *마지막 구간*만 **compact 평가**(짧은 출력)해 지연을 묶는다.

        - 풀 평가 윈도우는 새로 제출하지 않는다(7s씩 걸려 turn 종료를 막음).
        - 완료된 커버리지 끝(`_eval_covered_until`)~now를 compact로 1회 평가 → 발화 중 못 끝낸/
          안 돈/실패한 마지막 구간이 항상 즉시 반영된다(체감 ≤목표). 길이는 assemble 캡(비디오
          16프레임·오디오 30s)이 자동 슬라이드. 짧은 답변(풀 평가 0개)은 전체를 compact로 1회.
        - compact tail은 **전용 tail 레인**에 올려 비언어/풀 평가에 절대 안 밀린다.
        - 발화 중 완성된 풀 윈도우는 이미 emit돼 있고, end_turn은 그것들을 기다리지 않는다(집계 없음).
          아직 도는 풀 평가는 의도적으로 버린다(그 구간은 compact tail이 재커버)."""
        nv_jobs: list[tuple[float, float, list[bytes], bytes]] = []
        tail_jobs: list[tuple[float, float, list[bytes], bytes]] = []
        with self._lock:
            # 비언어: due 윈도우 + tail (저지연이라 그대로)
            while self._next_nv_end <= now_s:
                start = self._next_nv_end - self.nv_w
                self._next_nv_end += self.nv_w
                frames, pcm = self._slice(start, start + self.nv_w)
                nv_jobs.append((start, self.nv_w, frames, pcm))
            nv_tail_start = self._next_nv_end - self.nv_w
            if now_s - nv_tail_start > 0.5:  # 0.5s 미만 자투리 무시
                frames, pcm = self._slice(nv_tail_start, now_s)
                nv_jobs.append((nv_tail_start, now_s - nv_tail_start, frames, pcm))
            # 평가 compact tail: 완료된 커버리지 끝~now.
            tail_start = self._eval_covered_until
            tail_dur = now_s - tail_start
            # 짧은 답변(풀 평가 0개)이면 전체가 tail이라 무조건 평가; 그 외엔 1s 미만 자투리만 무시
            # (직전 풀 윈도우가 이미 커버한 끝자락 sliver는 스킵).
            whole_answer = self._eval_covered_until == 0.0
            if tail_dur > 0.0 and (whole_answer or tail_dur > 1.0):
                frames, pcm = self._slice(tail_start, now_s)
                tail_jobs.append((tail_start, tail_dur, frames, pcm))
        futures: list[Future] = []
        # compact tail → 전용 tail 레인(절대 경합 없음). 비언어 tail/잔여는 빠른 레인.
        for (start, dur, frames, pcm) in tail_jobs:
            if frames and pcm:
                futures.append(self._submit(self._tail_exec, self._do_eval, start, dur, frames, pcm, True))
        for (start, dur, frames, pcm) in nv_jobs:
            if frames:
                futures.append(self._submit(self._nv_exec, self._do_nv, start, dur, frames, pcm))
        if futures:  # compact tail(+비언어 tail)만 기다림 — 발화중 풀 윈도우는 안 기다림
            wait(futures, timeout=self.eot_deadline_s)

    def close(self) -> None:
        """신호 수용 중단(_closed) 후 소유한 실행기 종료. 주입 실행기는 호출자 책임.
        end_turn 후 호출되면 아직 도는 풀 평가의 뒤늦은 emit은 _closed 가드로 no-op."""
        with self._out_lock:
            self._closed = True
        if self._owns_exec:
            self._nv_exec.shutdown(wait=False)
            self._eval_exec.shutdown(wait=False)
            self._tail_exec.shutdown(wait=False)
