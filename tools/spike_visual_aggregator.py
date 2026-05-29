#!/usr/bin/env python3
"""smart 집계기 스파이크 — per-frame 관찰 타임라인 → LLM 질적 집계.

D7에서 '프레임별 분석 + 집계' 아키텍처를 확정했고, 집계를 crude run-collapse로 했다.
이 스파이크는 집계의 절반을 검증한다: **per-frame 관찰 타임라인을 LLM에 텍스트로 줘
질적 시간동역학을 뽑는 smart 집계기**.

  Part A (손가락 sanity): v2 타임라인(0.5s 간격 손가락 수, 잡음 포함)을 LLM 집계기에 줘
    의도된 시퀀스를 복원 → GT 5 2 10 9 4 2 1 4 5 10 / crude collapse와 대조.
    ※ per-frame 카운트 오류(4↔5)는 못 고친다(garbage in) — 집계기는 타임라인 잡음만 정리.

  Part B (시선/고개 본검증, vid_0001): 진짜 목표 신호. 매 Δs per-frame 구조화 관찰
    (시선/고개/손동작) → 타임라인 → LLM 집계로 면접관 관점 질적 요약.
    ※ vid_0001은 시선/고개가 대체로 안정(극적 움직임 GT 없음) → 검증 초점은
      per-frame 판단 신뢰성 + 집계 일관성 + 없는 움직임 환각 안 함(false positive).

집계기는 end-of-turn 텍스트 호출 1회(per-frame은 발화 중 분산). latency 측정.
실행: PYTHONPATH=src python3 tools/spike_visual_aggregator.py
"""
from __future__ import annotations

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
VID0001 = Path("/home/kio/workspace/gje/vid_0001.mp4")
VID0001_DUR = 43.46
FINGER_TIMELINE = Path(".sisyphus/evidence/spike-visual-temporal-v2.json")
GROUND_TRUTH_FINGERS = [5, 2, 10, 9, 4, 2, 1, 4, 5, 10]
EVIDENCE = Path(".sisyphus/evidence/spike-visual-aggregator.json")

GAZE_FRAME_PROMPT = (
    "이 화상면접 프레임을 보고 딱 한 줄로만 답하세요. 형식 그대로:\n"
    "시선=<카메라|위|아래|왼쪽|오른쪽>; 고개=<정면|왼쪽돌림|오른쪽돌림|기울임|숙임>; 손동작=<있음|없음>\n"
    "추측하지 말고 보이는 대로."
)
AGG_GAZE_PROMPT = (
    "다음은 한 지원자의 화상면접 답변을 시간 순서대로 관찰한 비언어 단서 타임라인입니다"
    "(각 줄: 초 / 시선 / 고개 / 손동작). 면접관 관점에서 시선 처리·고개 움직임·손동작 사용을 "
    "시간 흐름에 따라 질적으로 평가하세요. 전반적으로 안정적인지, 시선을 회피하거나 산만한 "
    "구간이 있는지, 눈에 띄는 변화 시점이 있는지 구체적으로 짚고 개선점도 적으세요."
)
AGG_FINGER_PROMPT = (
    "다음은 0.5초 간격으로 매 프레임 손가락 개수를 센 관찰 타임라인입니다"
    "(손을 내린 0, 전환/블러로 인한 잡음 포함). 화자가 의도적으로 들어 보인 손가락 개수만 "
    "시간 순서대로 복원하세요. 설명 없이 숫자만 쉼표로."
)


def frame_b64(video: Path, at_s: float) -> str:
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
           "-ss", f"{at_s:.3f}", "-i", str(video),
           "-frames:v", "1", "-q:v", "2", "-f", "image2", "pipe:1"]
    out = subprocess.run(cmd, capture_output=True, check=True, timeout=15).stdout
    return base64.b64encode(out).decode("ascii")


def chat(content: list[dict], *, max_tokens: int) -> tuple[str, float, float]:
    """stream → (text, ttft_s, total_s)."""
    body = {"model": MODEL, "messages": [{"role": "user", "content": content}],
            "max_tokens": max_tokens, "temperature": 0.0, "stream": True}
    req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    start = time.monotonic()
    ttft = -1.0
    out: list[str] = []
    with urllib.request.urlopen(req, timeout=120) as resp:
        for raw in resp:
            line = raw.decode("utf-8").strip()
            if not line.startswith("data: "):
                continue
            d = line[6:]
            if d == "[DONE]":
                break
            delta = json.loads(d)["choices"][0]["delta"].get("content")
            if delta:
                if ttft < 0:
                    ttft = time.monotonic() - start
                out.append(delta)
    return "".join(out), ttft, time.monotonic() - start


def observe_frame(video: Path, at_s: float, prompt: str) -> str:
    b = frame_b64(video, at_s)
    txt, _, _ = chat([{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b}"}},
                      {"type": "text", "text": prompt}], max_tokens=48)
    return " ".join(txt.split())


def aggregate(timeline_text: str, prompt: str, max_tokens: int = 600) -> tuple[str, float, float]:
    return chat([{"type": "text", "text": prompt + "\n\n" + timeline_text}], max_tokens=max_tokens)


def part_a_fingers() -> dict:
    print("=== Part A: 손가락 sanity — 타임라인→LLM 집계 vs crude collapse vs GT ===")
    data = json.loads(FINGER_TIMELINE.read_text(encoding="utf-8"))
    times, counts = data["times_s"], data["timeline"]
    crude = data.get("stable_collapse")
    tl_text = "\n".join(f"{t:.1f}s: {c}" for t, c in zip(times, counts))
    text, ttft, total = aggregate(tl_text, AGG_FINGER_PROMPT, max_tokens=128)
    recovered = re.findall(r"\d+", text)
    print(f"  GT             : {GROUND_TRUTH_FINGERS}")
    print(f"  crude collapse : {crude}")
    print(f"  LLM 집계       : {text.strip()}  (TTFT {ttft:.2f}s)")
    return {"gt": GROUND_TRUTH_FINGERS, "crude_collapse": crude,
            "llm_aggregated_raw": text, "llm_aggregated_nums": [int(x) for x in recovered],
            "aggregator_ttft_s": ttft, "aggregator_total_s": total}


def part_b_gaze(dt: float = 1.5) -> dict:
    print(f"\n=== Part B: 시선/고개 본검증 (vid_0001, Δ={dt}s) ===")
    times = [round(t, 1) for t in _frange(1.0, VID0001_DUR - 1.0, dt)]
    b64s = [frame_b64(VID0001, t) for t in times]

    # per-frame 관찰 (병렬 = 라이브 발화중 분산처리 가정)
    par_start = time.monotonic()
    with ThreadPoolExecutor(max_workers=8) as ex:
        obs = list(ex.map(lambda b: _observe_b64(b, GAZE_FRAME_PROMPT), b64s))
    par_total = time.monotonic() - par_start

    tl_lines = [f"{t:.1f}s: {o}" for t, o in zip(times, obs)]
    print(f"  per-frame 관찰 {len(times)}장 (병렬 {par_total:.2f}s):")
    for ln in tl_lines:
        print("   ", ln)

    tl_text = "\n".join(tl_lines)
    summary, ttft, total = aggregate(tl_text, AGG_GAZE_PROMPT, max_tokens=600)
    print(f"\n  --- LLM 집계 질적 요약 (end-of-turn 1회, TTFT {ttft:.2f}s, total {total:.2f}s) ---")
    print(summary)
    return {"dt_s": dt, "times_s": times, "per_frame_obs": obs,
            "per_frame_parallel_total_s": par_total,
            "summary": summary, "aggregator_ttft_s": ttft, "aggregator_total_s": total}


def _observe_b64(b64: str, prompt: str) -> str:
    txt, _, _ = chat([{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                      {"type": "text", "text": prompt}], max_tokens=48)
    return " ".join(txt.split())


def _frange(lo: float, hi: float, step: float) -> list[float]:
    out, x = [], lo
    while x <= hi:
        out.append(x)
        x += step
    return out


def main() -> None:
    try:
        with urllib.request.urlopen("http://localhost:8000/v1/models", timeout=5) as r:
            assert MODEL in r.read().decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"vLLM 미기동: {exc}")

    results = {"part_a_fingers": part_a_fingers(), "part_b_gaze": part_b_gaze()}
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n증거: {EVIDENCE}")
    print("판정(사용자/육안): Part A 집계가 crude보다 깔끔한가(단 카운트 오류는 못 고침). "
          "Part B 시선/고개 per-frame이 신뢰할 만한가, 집계 요약이 정확·일관한가, 없는 움직임 환각 안 하나?")


if __name__ == "__main__":
    main()
