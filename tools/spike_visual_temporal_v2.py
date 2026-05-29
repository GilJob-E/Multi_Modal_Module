#!/usr/bin/env python3
"""시각 시간축 아키텍처 검증 v2 — 프레임별 분석 + 집계.

v1 진단: 다중 이미지를 한 프롬프트에 넣으면 시간 binding이 깨졌다(0,1,2,3,4,5 환각).
단, 단일 프레임 카운팅은 4/4 정확. 가설: '프레임별 단일 호출 → 타임라인 집계'면
시퀀스를 복원한다. 또 등간격 밀집(매 Δs)이면 transient 제스처(약 3.7s 간격)를 놓치지 않는다.

video.mp4(37s) GT(제스처): 5 2 10 9 4 2 1 4 5 10.

측정:
  - 매 Δs 단일 프레임 카운트 → (t, count) 타임라인 → 연속중복/안정 collapse → GT 대조.
  - latency: 순차 합 vs 병렬(ThreadPool) 합. 라이브에선 프레임이 턴 중 도착하므로
    이 비용은 'end-of-turn'이 아니라 발화 중에 분산·은닉된다(비전판 periodic 처리).

실행: PYTHONPATH=src python3 tools/spike_visual_temporal_v2.py [--dt 1.0]
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ENDPOINT = "http://localhost:8000/v1/chat/completions"
MODEL = "google/gemma-4-E4B-it"
VIDEO = Path("/home/kio/workspace/gje/video.mp4")
DURATION = 37.16
GROUND_TRUTH = [5, 2, 10, 9, 4, 2, 1, 4, 5, 10]
EVIDENCE = Path(".sisyphus/evidence/spike-visual-temporal-v2.json")

PROMPT = ("이 사진에서 사람이 카메라를 향해 펴 보인 손가락 총 개수(양손 합, 0~10)는? "
          "손이 안 보이거나 주먹이면 0. 숫자 하나만 출력.")


def frame_jpeg(at_s: float) -> str:
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
           "-ss", f"{at_s:.3f}", "-i", str(VIDEO),
           "-frames:v", "1", "-q:v", "2", "-f", "image2", "pipe:1"]
    out = subprocess.run(cmd, capture_output=True, check=True, timeout=15).stdout
    return base64.b64encode(out).decode("ascii")


def count_one(b64: str) -> tuple[int, float]:
    body = {"model": MODEL, "messages": [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        {"type": "text", "text": PROMPT}]}], "max_tokens": 8, "temperature": 0.0}
    req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    t = time.monotonic()
    with urllib.request.urlopen(req, timeout=60) as resp:
        txt = json.load(resp)["choices"][0]["message"]["content"]
    nums = re.findall(r"\d+", txt)
    return (int(nums[0]) if nums else -1), time.monotonic() - t


def collapse(seq: list[int]) -> list[int]:
    out: list[int] = []
    for v in seq:
        if v >= 0 and (not out or out[-1] != v):
            out.append(v)
    return out


def collapse_stable(timeline: list[int], min_run: int = 2) -> list[int]:
    """min_run번 연속 같은 값일 때만 제스처로 인정(전환/블러 잡음 억제)."""
    out: list[int] = []
    i = 0
    while i < len(timeline):
        j = i
        while j < len(timeline) and timeline[j] == timeline[i]:
            j += 1
        run = j - i
        if timeline[i] >= 0 and run >= min_run and (not out or out[-1] != timeline[i]):
            out.append(timeline[i])
        i = j
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dt", type=float, default=1.0, help="샘플 간격(초)")
    args = ap.parse_args()
    try:
        with urllib.request.urlopen("http://localhost:8000/v1/models", timeout=5) as r:
            assert MODEL in r.read().decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"vLLM 미기동: {exc}")

    times = [round(t, 2) for t in _frange(0.5, DURATION - 0.3, args.dt)]
    b64s = [frame_jpeg(t) for t in times]
    print(f"video {DURATION:.1f}s, Δ={args.dt}s → {len(times)} 프레임. GT: {GROUND_TRUTH}\n")

    # 순차 — per-frame latency 분포 + 타임라인
    seq_start = time.monotonic()
    timeline, per_lat = [], []
    for t, b in zip(times, b64s):
        c, dt = count_one(b)
        timeline.append(c)
        per_lat.append(dt)
        print(f"  t={t:5.1f}s → {c:>2}  ({dt*1000:5.0f}ms)")
    seq_total = time.monotonic() - seq_start

    # 병렬 — 라이브 동시처리 가정의 total
    par_start = time.monotonic()
    with ThreadPoolExecutor(max_workers=10) as ex:
        list(ex.map(lambda b: count_one(b), b64s))
    par_total = time.monotonic() - par_start

    naive = collapse(timeline)
    stable = collapse_stable(timeline, min_run=2)
    print(f"\n타임라인: {timeline}")
    print(f"naive collapse : {naive}")
    print(f"stable collapse: {stable}")
    print(f"GT             : {GROUND_TRUTH}")
    print(f"\nper-frame latency: 평균 {sum(per_lat)/len(per_lat)*1000:.0f}ms")
    print(f"순차 total {seq_total:.2f}s | 병렬(10) total {par_total:.2f}s ({len(times)}프레임)")
    print(f"→ 라이브: 이 {len(times)}프레임은 턴 중 분산 처리 → end-of-turn엔 집계만(거의 0).")

    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps({
        "ground_truth": GROUND_TRUTH, "dt_s": args.dt, "times_s": times,
        "timeline": timeline, "naive_collapse": naive, "stable_collapse": stable,
        "per_frame_latency_ms_avg": sum(per_lat) / len(per_lat) * 1000.0,
        "seq_total_s": seq_total, "parallel10_total_s": par_total, "n_frames": len(times),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n증거: {EVIDENCE}")


def _frange(lo: float, hi: float, step: float) -> list[float]:
    out, x = [], lo
    while x <= hi:
        out.append(x)
        x += step
    return out


if __name__ == "__main__":
    main()
