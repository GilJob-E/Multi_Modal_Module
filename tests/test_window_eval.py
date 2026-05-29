#!/usr/bin/env python3
"""WindowEvaluator 통합 테스트 — 실제 클립 윈도우로 두 채널 신호 산출 (서버 필요).

실행: PYTHONPATH=src python3 tests/test_window_eval.py
서버: bash sglang/launch-configs/vllm_e4b_audio.sh (E4B + video:1)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from local_infer import clip_stream  # noqa: E402
from local_infer.native_eval import WindowEvaluator  # noqa: E402
from local_infer.signals import NONVERBAL_STATES  # noqa: E402
from local_infer.vllm_client import default_vllm_client  # noqa: E402

CLIP = "/home/kio/workspace/gje/vid_0001.mp4"  # 신선 면접 답변(43.5s, 음성 포함)
EVIDENCE = Path(".sisyphus/evidence/m2-window-eval.json")


def main() -> int:
    client = default_vllm_client()
    try:
        client.health()
    except Exception as e:  # noqa: BLE001
        print(f"✗ 서버 미기동: {e}\n  bash sglang/launch-configs/vllm_e4b_audio.sh 후 재시도")
        return 1

    ev = WindowEvaluator(client=client)
    out: dict = {"clip": Path(CLIP).name}
    failed = 0

    # ② 16초 평가 윈도우
    frames16 = clip_stream.extract_frames(CLIP, start_s=0.0, dur_s=16.0, fps=1.0)
    pcm16 = clip_stream.extract_pcm(CLIP, start_s=0.0, dur_s=16.0)
    print(f"[②] 16s 윈도우: 프레임 {len(frames16)}장(1fps), PCM {len(pcm16)//2/16000:.1f}s")
    t0 = time.monotonic()
    es = ev.evaluate_window(frames16, pcm16, window_start_s=0.0, window_dur_s=16.0)
    dt = time.monotonic() - t0
    print(f"     {dt:.2f}s → verbal={list(es.verbal)} vocal={list(es.vocal)} "
          f"visual={list(es.visual)} obs={len(es.key_observations)}")
    try:
        assert es.verbal and es.vocal and es.visual, "빈 평가 축"
        assert es.key_observations, "key_observations 비어있음"
        print("  ✓ ② EvaluationSignal 세 축 + 관찰 채워짐")
    except AssertionError as e:
        failed += 1; print(f"  ✗ ②: {e}")
    out["evaluation"] = {"latency_s": round(dt, 2), "signal": es.to_dict()}

    # ① 3초 비언어 read
    frames3 = clip_stream.extract_frames(CLIP, start_s=6.0, dur_s=3.0, fps=1.0)
    pcm3 = clip_stream.extract_pcm(CLIP, start_s=6.0, dur_s=3.0)
    print(f"[①] 3s 윈도우: 프레임 {len(frames3)}장")
    t0 = time.monotonic()
    ns = ev.read_nonverbal(frames3, pcm3, t=7.5, window_s=3.0)
    dt = time.monotonic() - t0
    print(f"     {dt:.2f}s → state={ns.state} intensity={ns.intensity} note={ns.note!r}")
    try:
        assert ns.state in NONVERBAL_STATES, f"잘못된 state {ns.state}"
        assert 0.0 <= ns.intensity <= 1.0
        print("  ✓ ① NonVerbalSignal 유효 state/intensity")
    except AssertionError as e:
        failed += 1; print(f"  ✗ ①: {e}")
    out["nonverbal"] = {"latency_s": round(dt, 2), "signal": ns.to_dict()}

    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"=== {'ALL PASS' if not failed else f'{failed} FAILED'} === 증거: {EVIDENCE}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
