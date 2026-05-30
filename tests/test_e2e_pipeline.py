#!/usr/bin/env python3
"""M5 end-to-end 검증 — 클립을 시뮬 라이브 턴으로 실제 파이프라인에 흘린다(서버 필요).

핵심 측정 = **end-of-turn 확정 지연**(activityEnd→마지막 신호). 성공기준 = 체감 레이턴시:
compact tail로 **≤2.5s** 목표. 발화 중 평가는 백그라운드 실행이라 채널①(아바타 backchannel)을
막지 않는다. per-window 지연도 클립 길이 범위로 측정(과대일반화 금지: 클립별 보고).
실행: PYTHONPATH=src .venv/bin/python tests/test_e2e_pipeline.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from local_infer import clip_stream  # noqa: E402
from local_infer.native_eval import WindowEvaluator  # noqa: E402
from local_infer.signals import EvaluationSignal, NonVerbalSignal  # noqa: E402
from local_infer.turn_pipeline import SlidingWindowPipeline  # noqa: E402
from local_infer.vllm_client import default_vllm_client  # noqa: E402

# 음성 있는 면접 답변 클립만 (AV 평가는 오디오 필수).
# video.mp4(37.2s 손가락 GT)는 오디오 트랙이 없어 e2e에서 제외 — 결정목록 참조.
CLIPS = [
    "/home/kio/workspace/gje/vid_0001.mp4",  # 43.5s — 턴이 16s 경계서 멀리 끝남(긴 tail = eot worst-case)
    "/home/kio/workspace/gje/vid_0033.mp4",  # 50.3s — 턴이 경계 직후 끝남(짧은 tail)
]
SR = 16000
EOT_TARGET_S = 2.5  # 성공기준: end-of-turn 확정 지연 ≤ 2.5s (체감 레이턴시)
EVIDENCE = Path(".sisyphus/evidence/m5-e2e.json")


class TimingEval:
    """실제 WindowEvaluator 래퍼 — 호출별 (channel, latency, compact) 기록.
    워커 스레드에서 호출되므로 list.append(원자적)만 사용."""

    def __init__(self, real: WindowEvaluator) -> None:
        self.real = real
        self.records: list[tuple[str, float, bool]] = []

    def read_nonverbal(self, *a, **k) -> NonVerbalSignal:
        t0 = time.monotonic()
        s = self.real.read_nonverbal(*a, **k)
        self.records.append(("nonverbal", time.monotonic() - t0, False))
        return s

    def evaluate_window(self, *a, **k) -> EvaluationSignal:
        t0 = time.monotonic()
        s = self.real.evaluate_window(*a, **k)
        self.records.append(("evaluation", time.monotonic() - t0, bool(k.get("compact", False))))
        return s


def _dur(clip: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", clip],
        capture_output=True, text=True, timeout=15,
    )
    return float(out.stdout.strip())


def _stats(xs: list[float]) -> dict:
    return {"n": len(xs), "min": round(min(xs), 2), "max": round(max(xs), 2),
            "mean": round(sum(xs) / len(xs), 2)} if xs else {"n": 0}


def _sort_key(sig) -> float:
    return sig.t if isinstance(sig, NonVerbalSignal) else sig.window_start_s


def run_clip(clip: str, real_eval: WindowEvaluator) -> dict:
    dur = _dur(clip)
    frames = clip_stream.extract_frames(clip, start_s=0.0, dur_s=dur, fps=1.0)
    pcm_all = clip_stream.extract_pcm(clip, start_s=0.0, dur_s=dur, sample_rate=SR)
    print(f"\n[{Path(clip).name}] {dur:.1f}s, {len(frames)} frames(1fps), pcm {len(pcm_all)//2/SR:.1f}s")

    timing = TimingEval(real_eval)
    pipe = SlidingWindowPipeline(timing, nonverbal_window_s=3.0, eval_window_s=16.0,
                                 src_fps=1.0, sample_rate=SR)  # 백그라운드(스레드) 실행
    for i, jpeg in enumerate(frames):
        pipe.add_frame(i + 0.5, jpeg)
    chunk = SR * 2
    for i in range(int(dur)):
        pipe.add_audio(float(i), pcm_all[i * chunk:(i + 1) * chunk])

    # 발화 중 1s 간격 poll(백그라운드 제출). 라이브에선 16s마다 풀 평가가 다음 경계 전 완료되므로
    # wait_idle로 그 정상상태(발화 중 분산처리 완료)를 만든 뒤 end-of-turn을 격리 측정한다.
    for now in range(1, int(dur) + 1):
        pipe.poll(float(now))
    pipe.wait_idle(timeout=180)
    emitted: list = pipe.drain()

    # end-of-turn: 확정 지연 측정(다음질문 반영의 임계 경로 = 체감 레이턴시)
    t0 = time.monotonic()
    pipe.end_turn(dur)
    finalize_s = time.monotonic() - t0
    pipe.wait_idle(timeout=10)
    emitted += pipe.drain()
    pipe.close()

    emitted.sort(key=_sort_key)  # 완료순 → 시간순(타임라인 가독성; 신호는 타임스탬프로 자기기술)

    nv = [d for (c, d, _comp) in timing.records if c == "nonverbal"]
    ev_full = [d for (c, d, comp) in timing.records if c == "evaluation" and not comp]
    ev_tail = [d for (c, d, comp) in timing.records if c == "evaluation" and comp]
    n_nv = sum(1 for s in emitted if isinstance(s, NonVerbalSignal))
    n_ev = sum(1 for s in emitted if isinstance(s, EvaluationSignal))
    eot_ok = finalize_s <= EOT_TARGET_S
    print(f"  신호: 비언어 {n_nv}, 평가 {n_ev}(풀 {len(ev_full)}+tail {len(ev_tail)}) | "
          f"비언어지연 {_stats(nv)} | 풀평가지연 {_stats(ev_full)} | compact-tail지연 {_stats(ev_tail)}")
    print(f"  end-of-turn 확정 지연: {finalize_s:.2f}s  (목표 ≤{EOT_TARGET_S}s) {'✓' if eot_ok else '✗ 초과'}")

    timeline = []
    for s in emitted:
        ch = "nonverbal" if isinstance(s, NonVerbalSignal) else "evaluation"
        timeline.append({"channel": ch, **s.to_dict()})

    return {
        "clip": Path(clip).name, "duration_s": round(dur, 1),
        "frames": len(frames), "signals": {"nonverbal": n_nv, "evaluation": n_ev},
        "nonverbal_latency_s": _stats(nv),
        "evaluation_full_latency_s": _stats(ev_full),
        "evaluation_tail_latency_s": _stats(ev_tail),
        "endofturn_finalize_s": round(finalize_s, 2),
        "eot_target_s": EOT_TARGET_S,
        "eot_ok": eot_ok,
        "timeline": timeline,
    }


def main() -> int:
    client = default_vllm_client()
    try:
        client.health()
    except Exception as e:  # noqa: BLE001
        print(f"✗ 서버 미기동: {e}")
        return 1

    real = WindowEvaluator(client=client)
    results = []
    failed = 0
    for clip in CLIPS:
        if not Path(clip).exists():
            print(f"  (skip, 없음: {clip})")
            continue
        r = run_clip(clip, real)
        results.append(r)
        if r["signals"]["evaluation"] < 1 or r["signals"]["nonverbal"] < 1:
            failed += 1
            print(f"  ✗ {r['clip']}: 신호 부족")
        if not r["eot_ok"]:
            failed += 1
            print(f"  ✗ {r['clip']}: end-of-turn {r['endofturn_finalize_s']}s > 목표 {EOT_TARGET_S}s "
                  f"(tail_max_tokens 낮추거나 compact 스키마 더 축소)")

    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps({"clips": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== {'ALL PASS' if not failed else f'{failed} FAILED'} === 증거: {EVIDENCE}")
    print("길이 범위 요약(과대일반화 금지 — 클립별):")
    for r in results:
        print(f"  {r['clip']:16s} {r['duration_s']:5.1f}s  비언어 {r['nonverbal_latency_s'].get('mean','?')}s "
              f"풀평가 {r['evaluation_full_latency_s'].get('mean','?')}s  "
              f"확정 {r['endofturn_finalize_s']}s {'✓' if r['eot_ok'] else '✗'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
