#!/usr/bin/env python3
"""SlidingWindowPipeline 스케줄링 단위 테스트 — fake evaluator(GPU 불필요).

실제 추론은 M2(test_window_eval)·M5(e2e)에서 검증. 여기선 윈도우 분할·cadence·
end-of-turn tail flush 로직만 본다.

실행: PYTHONPATH=src python3 tests/test_turn_pipeline.py
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from local_infer.signals import EvaluationSignal, NonVerbalSignal  # noqa: E402
from local_infer.turn_pipeline import InlineExecutor, SlidingWindowPipeline  # noqa: E402


class FakeEvaluator:
    def __init__(self) -> None:
        self.nv_calls: list[tuple[float, float, int]] = []  # (t, window_s, n_frames)
        self.eval_calls: list[tuple[float, float, int, bool]] = []  # (start, dur, n_frames, compact)

    def read_nonverbal(self, jpeg_frames, pcm, *, t, window_s, src_fps=1.0, sample_rate=16000):
        self.nv_calls.append((t, window_s, len(jpeg_frames)))
        return NonVerbalSignal(t=t, window_s=window_s, state="engaged", intensity=0.5)

    def evaluate_window(self, jpeg_frames, pcm, *, window_start_s, window_dur_s, src_fps=1.0, sample_rate=16000, compact=False):
        self.eval_calls.append((window_start_s, window_dur_s, len(jpeg_frames), compact))
        return EvaluationSignal(window_start_s=window_start_s, window_dur_s=window_dur_s, compact=compact)


def test_cadence_and_endturn():
    fake = FakeEvaluator()
    emitted: list = []
    pipe = SlidingWindowPipeline(fake, on_signal=emitted.append, nonverbal_window_s=3.0,
                                 eval_window_s=16.0, executor=InlineExecutor())

    # 20초 턴: 1fps 프레임 20장 + 1s 오디오 청크 20개
    for i in range(20):
        pipe.add_frame(i + 0.5, b"\xff\xd8jpeg")  # 더미 JPEG 바이트
        pipe.add_audio(float(i), b"\x00\x00" * 16000)  # 1s 무음

    # 발화 중 점진 poll
    for now in (3, 6, 9, 12, 15, 18):
        pipe.poll(float(now))
    # 발화 종료
    pipe.end_turn(20.0)

    nv_starts = [round(t - w / 2, 1) for (t, w, _) in fake.nv_calls]
    eval_windows = [(s, d) for (s, d, _n, _c) in fake.eval_calls]
    print(f"  nonverbal windows(start): {nv_starts}")
    print(f"  eval windows(start,dur,compact): {fake.eval_calls}")

    # 비언어: [0,3),[3,6),[6,9),[9,12),[12,15),[15,18) = 6 + tail [18,20) = 7
    assert len(fake.nv_calls) == 7, f"nv calls {len(fake.nv_calls)} != 7"
    assert nv_starts[:6] == [0.0, 3.0, 6.0, 9.0, 12.0, 15.0], nv_starts
    # 평가: 발화중 풀 [0,16) 1개 + end-of-turn compact tail [16,20) 1개 = 2
    assert len(fake.eval_calls) == 2, f"eval calls {len(fake.eval_calls)} != 2"
    assert eval_windows[0] == (0.0, 16.0), eval_windows
    assert abs(eval_windows[1][0] - 16.0) < 1e-6 and abs(eval_windows[1][1] - 4.0) < 1e-6, eval_windows
    # 발화중 풀 윈도우는 비-compact, end-of-turn tail은 compact(짧은 출력 → ≤지연목표)
    assert fake.eval_calls[0][3] is False, "발화중 풀 윈도우는 compact 아님"
    assert fake.eval_calls[1][3] is True, "end-of-turn tail은 compact"
    # emit 순서·개수 일치(집계 없이 per-window 그대로)
    assert len(emitted) == 7 + 2, len(emitted)
    # 첫 16s 평가 윈도우는 16프레임을 받았는가(1fps)
    assert fake.eval_calls[0][2] == 16, f"eval[0] frames {fake.eval_calls[0][2]}"
    print("  ✓ cadence(①3s/②16s) + end-of-turn compact tail + per-window emit(집계 없음)")


def test_no_aggregation_emits_each():
    """파이프라인이 신호를 병합하지 않고 윈도우마다 따로 emit하는지."""
    fake = FakeEvaluator()
    emitted: list = []
    pipe = SlidingWindowPipeline(fake, on_signal=emitted.append, nonverbal_window_s=3.0,
                                 eval_window_s=16.0, executor=InlineExecutor())
    for i in range(6):
        pipe.add_frame(i + 0.5, b"\xff\xd8j")
        pipe.add_audio(float(i), b"\x00\x00" * 16000)
    pipe.poll(6.0)
    assert all(isinstance(s, NonVerbalSignal) for s in emitted), "병합/변형 없이 per-window NonVerbalSignal"
    assert len(emitted) == 2, emitted  # [0,3),[3,6)
    print("  ✓ per-window 신호 그대로 emit (병합/집계 없음)")


class SlowFake:
    """비언어 read는 즉시, evaluate_window는 느림(sleep) — 실 스레드풀에서 레인 독립/race 검증용."""

    def __init__(self, eval_delay: float = 1.0) -> None:
        self.eval_delay = eval_delay
        self._lock = threading.Lock()
        self.eval_windows: list[tuple[float, float, bool]] = []  # (start, dur, compact)
        self.nv_count = 0

    def read_nonverbal(self, jpeg_frames, pcm, *, t, window_s, src_fps=1.0, sample_rate=16000):
        with self._lock:
            self.nv_count += 1
        return NonVerbalSignal(t=t, window_s=window_s, state="engaged", intensity=0.5)

    def evaluate_window(self, jpeg_frames, pcm, *, window_start_s, window_dur_s, src_fps=1.0, sample_rate=16000, compact=False):
        time.sleep(self.eval_delay)  # ~7s 풀 평가를 축소 모사
        with self._lock:
            self.eval_windows.append((window_start_s, window_dur_s, compact))
        return EvaluationSignal(window_start_s=window_start_s, window_dur_s=window_dur_s, compact=compact)


def test_channel1_not_blocked_by_channel2():
    """발화 중 무거운 평가(채널②)가 도는 동안 비언어 read(채널①)가 안 막히는지 — 레인 독립 (실 스레드)."""
    fake = SlowFake(eval_delay=1.0)
    pipe = SlidingWindowPipeline(fake, nonverbal_window_s=3.0, eval_window_s=16.0)  # 실제 3-레인 스레드풀
    for i in range(20):
        pipe.add_frame(i + 0.5, b"\xff\xd8j")
        pipe.add_audio(float(i), b"\x00\x00" * 16000)
    pipe.poll(16.0)  # 비언어 5개(즉시) + 풀 평가 1개(1.0s) 백그라운드 제출
    t0 = time.monotonic()
    got: list = []
    while time.monotonic() - t0 < 0.5:
        got += [s for s in pipe.drain() if isinstance(s, NonVerbalSignal)]
        if len(got) >= 5:
            break
        time.sleep(0.01)
    nv_latency = time.monotonic() - t0
    eval_done = any(not c for (_s, _d, c) in fake.eval_windows)  # 평가가 벌써 끝났으면 모사가 너무 빠름
    pipe.wait_idle(timeout=5)
    pipe.close()
    assert len(got) >= 5, f"비언어 {len(got)}/5 — 1.0s 평가에 막힘?"
    assert not eval_done, "평가가 0.5s 안에 끝남 — 동시성 테스트 무효(머신 과부하?)"
    assert nv_latency < 0.5, f"비언어 지연 {nv_latency:.2f}s — 평가에 막힌 듯(레인 미분리?)"
    print(f"  ✓ 채널① 비언어 5개가 채널②(1.0s 평가) 도는 중 {nv_latency*1000:.0f}ms에 떨어짐(레인 독립)")


def test_no_duplicate_under_concurrent_poll():
    """동시 poll 다수에도 같은 윈도우를 두 번 추론하지 않는지(race-free, 실 스레드)."""
    fake = SlowFake(eval_delay=0.1)
    pipe = SlidingWindowPipeline(fake, nonverbal_window_s=3.0, eval_window_s=16.0)
    for i in range(20):
        pipe.add_frame(i + 0.5, b"\xff\xd8j")
        pipe.add_audio(float(i), b"\x00\x00" * 16000)
    threads = [threading.Thread(target=pipe.poll, args=(16.0,)) for _ in range(12)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    pipe.wait_idle(timeout=5)
    pipe.close()
    full = [(s, d) for (s, d, c) in fake.eval_windows if not c]
    assert full == [(0.0, 16.0)], f"동시 poll에서 eval 중복/누락 제출: {fake.eval_windows}"
    assert fake.nv_count == 5, f"비언어 중복/누락: {fake.nv_count} != 5 ([0,3)..[12,15))"
    print(f"  ✓ 동시 poll 12개 → eval 1회·비언어 5회만(race-free): eval={full} nv={fake.nv_count}")


def test_short_turn_gets_compact_eval():
    """16s 미만 짧은 답변(풀 평가 0개)도 end_turn에서 전체를 compact로 1회 평가하는지(신호 누락 방지)."""
    fake = FakeEvaluator()
    emitted: list = []
    pipe = SlidingWindowPipeline(fake, on_signal=emitted.append, nonverbal_window_s=3.0,
                                 eval_window_s=16.0, executor=InlineExecutor())
    for i in range(9):  # 9초 답변
        pipe.add_frame(i + 0.5, b"\xff\xd8j")
        pipe.add_audio(float(i), b"\x00\x00" * 16000)
    for now in (3, 6, 9):
        pipe.poll(float(now))
    pipe.end_turn(9.0)
    evals = [(s, d, c) for (s, d, _n, c) in fake.eval_calls]
    assert len(evals) == 1 and evals[0][2] is True, f"짧은 답변 compact eval 누락: {evals}"
    assert abs(evals[0][0] - 0.0) < 1e-6 and abs(evals[0][1] - 9.0) < 1e-6, evals
    assert any(isinstance(s, EvaluationSignal) and s.compact for s in emitted), "compact 평가 신호 없음"
    print(f"  ✓ 9s 짧은 답변 → 전체 [0,9) compact 평가 1회(누락 없음): {evals}")


class FailingFake(FakeEvaluator):
    """발화중 풀 평가 [0,16)에서 예외 — 실패 윈도우가 compact tail로 재커버되는지 검증."""

    def evaluate_window(self, jpeg_frames, pcm, *, window_start_s, window_dur_s, src_fps=1.0, sample_rate=16000, compact=False):
        if not compact and window_start_s == 0.0:
            raise ValueError("simulated eval failure on [0,16)")
        return super().evaluate_window(jpeg_frames, pcm, window_start_s=window_start_s,
                                       window_dur_s=window_dur_s, compact=compact)


def test_failed_eval_window_recovered_by_tail():
    """발화중 풀 평가가 실패해도 그 구간이 covered_until을 전진시키지 않아 end_turn compact tail이
    재커버하는지(연속-prefix 추적 → coverage gap 방지). 실패는 로깅되고 파이프라인은 안 죽는다."""
    import logging
    logging.getLogger("local_infer.turn_pipeline").setLevel(logging.CRITICAL)  # 기대된 에러로그 숨김
    fake = FailingFake()
    pipe = SlidingWindowPipeline(fake, nonverbal_window_s=3.0, eval_window_s=16.0, executor=InlineExecutor())
    for i in range(20):
        pipe.add_frame(i + 0.5, b"\xff\xd8j")
        pipe.add_audio(float(i), b"\x00\x00" * 16000)
    for now in range(1, 21):
        pipe.poll(float(now))  # [0,16) 풀 평가 제출 → 실패(예외, 로깅·삼킴, covered_until 전진 안 함)
    pipe.end_turn(20.0)
    fulls = [(s, d) for (s, d, _n, c) in fake.eval_calls if not c]
    tails = [(s, d) for (s, d, _n, c) in fake.eval_calls if c]
    # 실패한 [0,16)은 성공 기록 없음. covered_until=0 → whole_answer → compact tail [0,20) 재커버.
    assert fulls == [], f"실패한 [0,16)이 성공 처리됨? {fake.eval_calls}"
    assert len(tails) == 1 and abs(tails[0][0]) < 1e-6, f"compact tail이 [0,..)를 재커버 안 함: {tails}"
    print(f"  ✓ 실패한 풀 평가 [0,16)을 compact tail {tails[0]}이 재커버(연속-prefix, gap 없음)")


def main() -> int:
    tests = [test_cadence_and_endturn, test_no_aggregation_emits_each,
             test_channel1_not_blocked_by_channel2, test_no_duplicate_under_concurrent_poll,
             test_short_turn_gets_compact_eval, test_failed_eval_window_recovered_by_tail]
    print(f"=== turn_pipeline tests ({len(tests)}) ===")
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:  # noqa: BLE001
            failed += 1
            import traceback
            print(f"  ✗ {t.__name__}: {e}")
            traceback.print_exc()
    print(f"=== {'ALL PASS' if not failed else f'{failed} FAILED'} ===")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
