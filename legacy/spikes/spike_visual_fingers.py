#!/usr/bin/env python3
"""시각 시간축 ground-truth 검증 — 손가락 개수 시퀀스 + latency.

video.mp4(37s, 320x240): 화자가 손가락을 5 2 10 9 4 2 1 4 5 10 순으로 바꾼다(10 제스처).
정답을 아는 순수 visual 시간축 테스트(오디오 무관). 프레임 N장을 등간격 샘플 → 시간순
손가락 수 나열 요청 → ground truth와 대조. N별 TTFT/total로 '시각 시간 해상도의 prefill
비용'(오디오와 달리 프레임 수에 비례)을 함께 본다.

  - N=4  : 현재 launch image 제약(=4)에서 가능한 최대 → 10 제스처를 담을 수 없음(under-sampling).
  - N=10 : 제스처 수와 동수.
  - N=16 : 등간격 2.3s(<3.7s 제스처 간격) → 각 제스처를 적어도 한 번 포착 기대.

실행: PYTHONPATH=src python3 tools/spike_visual_fingers.py
서빙: image 제약 ≥16 필요(vllm_e4b_audio.sh image:16).
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ENDPOINT = "http://localhost:8000/v1/chat/completions"
MODEL = "google/gemma-4-E4B-it"
VIDEO = Path("/home/kio/workspace/gje/video.mp4")
DURATION = 37.16
GROUND_TRUTH = [5, 2, 10, 9, 4, 2, 1, 4, 5, 10]
EVIDENCE = Path(".sisyphus/evidence/spike-visual-fingers.json")

PROMPT = (
    "다음 이미지들은 한 영상에서 시간 순서대로 등간격으로 추출한 프레임입니다. "
    "각 프레임에서 화자가 카메라를 향해 펴 보인 손가락의 총 개수(양손 합, 0~10)를 "
    "프레임 순서대로 세어, 숫자만 쉼표로 구분해 나열하세요. 설명 없이 숫자 목록만."
)


def frame_part(at_s: float) -> dict:
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-ss", f"{at_s:.3f}", "-i", str(VIDEO),
        "-frames:v", "1", "-q:v", "2", "-f", "image2", "pipe:1",
    ]
    out = subprocess.run(cmd, capture_output=True, check=True, timeout=15).stdout
    b64 = base64.b64encode(out).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}


def even_times(n: int) -> list[float]:
    # [0.5, dur-0.5] 등간격 n점(프레임 중앙 정렬).
    lo, hi = 0.5, DURATION - 0.5
    if n == 1:
        return [(lo + hi) / 2]
    return [lo + (hi - lo) * i / (n - 1) for i in range(n)]


def stream(content: list[dict], *, max_tokens: int = 256) -> tuple[int, str, float, float]:
    payload = {"model": MODEL, "messages": [{"role": "user", "content": content}],
               "max_tokens": max_tokens, "temperature": 0.0, "stream": True}
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    start = time.monotonic()
    ttft = -1.0
    chunks: list[str] = []
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue
                data = line[len("data: "):]
                if data == "[DONE]":
                    break
                delta = json.loads(data)["choices"][0]["delta"].get("content")
                if delta:
                    if ttft < 0:
                        ttft = time.monotonic() - start
                    chunks.append(delta)
            return 200, "".join(chunks), ttft, time.monotonic() - start
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace"), ttft, time.monotonic() - start


def parse_nums(text: str) -> list[int]:
    return [int(x) for x in re.findall(r"\d+", text)]


def collapse(seq: list[int]) -> list[int]:
    """연속 중복 제거 → 제스처 시퀀스 근사."""
    out: list[int] = []
    for v in seq:
        if not out or out[-1] != v:
            out.append(v)
    return out


def main() -> None:
    try:
        with urllib.request.urlopen("http://localhost:8000/v1/models", timeout=5) as r:
            assert MODEL in r.read().decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"vLLM 미기동: {exc}")

    print(f"video.mp4 {DURATION:.1f}s, ground truth(제스처 {len(GROUND_TRUTH)}개): {GROUND_TRUTH}\n")
    results = {"ground_truth": GROUND_TRUTH, "duration_s": DURATION, "runs": []}

    for n in (4, 10, 16):
        times = even_times(n)
        frames = [frame_part(t) for t in times]
        status, text, ttft, total = stream(frames + [{"type": "text", "text": PROMPT}])
        nums = parse_nums(text)
        print(f"--- N={n}프레임 (@{', '.join(f'{t:.1f}' for t in times)}s) ---")
        print(f"HTTP {status}  TTFT {ttft:.3f}s  total {total:.3f}s")
        print(f"모델 답: {text.strip()}")
        print(f"파싱: {nums}")
        if n >= 10:
            print(f"제스처 근사(연속중복 제거): {collapse(nums)}   vs GT {GROUND_TRUTH}")
        print()
        results["runs"].append({
            "n_frames": n, "sample_times_s": times, "status": status,
            "ttft_s": ttft, "total_s": total, "output": text,
            "parsed": nums, "collapsed": collapse(nums) if n >= 10 else None,
        })

    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"증거 기록: {EVIDENCE}")
    print("\n판정(사용자): 프레임 수가 늘면 제스처 시퀀스를 회복하는가? 손가락 수 자체를 정확히 세는가?")
    print("              latency가 프레임 수에 비례하는가(오디오와 달리 시각 시간 해상도의 비용)?")


if __name__ == "__main__":
    main()
