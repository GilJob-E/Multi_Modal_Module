#!/usr/bin/env python3
"""SlidingWindowPipeline 스케줄링 단위 테스트 — fake evaluator(GPU 불필요).

실제 추론은 M2(test_window_eval)·M5(e2e)에서 검증. 여기선 윈도우 분할·cadence·
end-of-turn tail flush 로직만 본다.

실행: PYTHONPATH=src python3 tests/test_turn_pipeline.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from local_infer.signals import EvaluationSignal, NonVerbalSignal  # noqa: E402
from local_infer.turn_pipeline import SlidingWindowPipeline  # noqa: E402


class FakeEvaluator:
    def __init__(self) -> None:
        self.nv_calls: list[tuple[float, float, int]] = []  # (t, window_s, n_frames)
        self.eval_calls: list[tuple[float, float, int]] = []  # (start, dur, n_frames)

    def read_nonverbal(self, jpeg_frames, pcm, *, t, window_s, src_fps=1.0, sample_rate=16000):
        self.nv_calls.append((t, window_s, len(jpeg_frames)))
        return NonVerbalSignal(t=t, window_s=window_s, state="engaged", intensity=0.5)

    def evaluate_window(self, jpeg_frames, pcm, *, window_start_s, window_dur_s, src_fps=1.0, sample_rate=16000):
        self.eval_calls.append((window_start_s, window_dur_s, len(jpeg_frames)))
        return EvaluationSignal(window_start_s=window_start_s, window_dur_s=window_dur_s)


def test_cadence_and_endturn():
    fake = FakeEvaluator()
    emitted: list = []
    pipe = SlidingWindowPipeline(fake, on_signal=emitted.append, nonverbal_window_s=3.0, eval_window_s=16.0)

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
    eval_windows = [(s, d) for (s, d, _) in fake.eval_calls]
    print(f"  nonverbal windows(start): {nv_starts}")
    print(f"  eval windows(start,dur): {eval_windows}")

    # 비언어: [0,3),[3,6),[6,9),[9,12),[12,15),[15,18) = 6 + tail [18,20) = 7
    assert len(fake.nv_calls) == 7, f"nv calls {len(fake.nv_calls)} != 7"
    assert nv_starts[:6] == [0.0, 3.0, 6.0, 9.0, 12.0, 15.0], nv_starts
    # 평가: [0,16) 1개 + tail [16,20) 1개 = 2
    assert len(fake.eval_calls) == 2, f"eval calls {len(fake.eval_calls)} != 2"
    assert eval_windows[0] == (0.0, 16.0), eval_windows
    assert abs(eval_windows[1][0] - 16.0) < 1e-6 and abs(eval_windows[1][1] - 4.0) < 1e-6, eval_windows
    # emit 순서·개수 일치(집계 없이 per-window 그대로)
    assert len(emitted) == 7 + 2, len(emitted)
    # 첫 16s 평가 윈도우는 16프레임을 받았는가(1fps)
    assert fake.eval_calls[0][2] == 16, f"eval[0] frames {fake.eval_calls[0][2]}"
    print("  ✓ cadence(①3s/②16s) + end-of-turn tail flush + per-window emit(집계 없음)")


def test_no_aggregation_emits_each():
    """파이프라인이 신호를 병합하지 않고 윈도우마다 따로 emit하는지."""
    fake = FakeEvaluator()
    emitted: list = []
    pipe = SlidingWindowPipeline(fake, on_signal=emitted.append, nonverbal_window_s=3.0, eval_window_s=16.0)
    for i in range(6):
        pipe.add_frame(i + 0.5, b"\xff\xd8j")
        pipe.add_audio(float(i), b"\x00\x00" * 16000)
    pipe.poll(6.0)
    assert all(isinstance(s, NonVerbalSignal) for s in emitted), "병합/변형 없이 per-window NonVerbalSignal"
    assert len(emitted) == 2, emitted  # [0,3),[3,6)
    print("  ✓ per-window 신호 그대로 emit (병합/집계 없음)")


def main() -> int:
    tests = [test_cadence_and_endturn, test_no_aggregation_emits_each]
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
