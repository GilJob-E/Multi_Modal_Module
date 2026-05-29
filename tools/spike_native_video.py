#!/usr/bin/env python3
"""native video_url 경로 실측 — 시간축 binding kill-test.

배경: 검증된 전송은 image_url 프레임 + audio_url뿐. native `video_url` 경로는
PLAN 내내 "별도 실측 후"로 미뤄졌다. 핵심 질문: video_url이 multi-image가 깨뜨린
시간축 binding을 native로 살려서 holistic frames+audio보다 뭘 더 주는가?

가장 잔인한 검증 클립 = video.mp4(손가락 GT 5 2 10 9 4 2 1 4 5 10, 37.16s).
multi-image baseline(spike-visual-fingers.json)은 처참히 실패했다:
  4프레임 → "0, 5, 2, 0"   10프레임 → "0, 0, 1, 2, 3, 4, 5" (카운팅 환각).
video_url이 이 시퀀스를 회복하면 = video_url이 시간축을 산다 → 명분 성립.
똑같이 깨지면 = holistic frames가 천장, video_url은 추가 가치 없음.

실행: PYTHONPATH=src python3 tools/spike_native_video.py
종료 후: docker stop vllm-gemma4-e4b && nvidia-smi (GPU 위생)
"""
from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ENDPOINT = "http://localhost:8000/v1/chat/completions"
MODEL = "google/gemma-4-E4B-it"
HOST_VIDEO = Path("/home/kio/workspace/gje/video.mp4")
GT_FINGERS = [5, 2, 10, 9, 4, 2, 1, 4, 5, 10]
MULTI_IMAGE_BASELINE = {"4프레임": "0, 5, 2, 0", "10프레임": "0, 0, 1, 2, 3, 4, 5"}
EVIDENCE = Path(".sisyphus/evidence/spike-native-video.json")

# A. 시간순 시퀀스 — multi-image가 깨진 바로 그 과제.
SEQ_PROMPT = (
    "This video shows a hand holding up a number of fingers, which changes over time. "
    "Watch the whole video from start to end and report the number of fingers held up "
    "at each distinct moment, in chronological order, as a comma-separated list of integers. "
    "Only output the list."
)
# B. 질적 시간변화 묘사 — 실제 deliverable(면접 시간동역학)에 가까운 형태.
TEMPORAL_PROMPT = (
    "Describe how the hand gesture changes over the course of this video, from beginning "
    "to end. Walk through it in temporal order: what happens first, then next, then at the end."
)


def stream_chat(content: list[dict], *, max_tokens: int = 512) -> tuple[int, str, float, float]:
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "stream": True,
    }
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
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
        total = time.monotonic() - start
        return exc.code, exc.read().decode("utf-8", errors="replace"), ttft, total


def video_part() -> dict:
    raw = HOST_VIDEO.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{b64}"}}


def main() -> None:
    print(f"=== native video_url kill-test ({HOST_VIDEO.name}, GT={GT_FINGERS}) ===")
    print(f"multi-image baseline(실패): {MULTI_IMAGE_BASELINE}\n")
    vid = video_part()
    print(f"video data URL: {len(vid['video_url']['url'])/1024:.0f} KB\n")

    results = {}

    # A. 시간순 시퀀스 (결정적 비교)
    s, text, ttft, total = stream_chat([vid, {"type": "text", "text": SEQ_PROMPT}], max_tokens=128)
    print(f"[A 시간순 시퀀스] HTTP {s}  TTFT {ttft:.2f}s  total {total:.2f}s")
    print("-" * 60); print(text); print("-" * 60)
    print(f"GT: {GT_FINGERS}\n")
    results["sequence"] = {"status": s, "ttft_s": ttft, "total_s": total, "output": text}

    if s != 200:
        print("NO-GO: video_url 전송이 HTTP 200이 아님. payload/슬롯/포맷 점검.")
        EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE.write_text(json.dumps(
            {"model": MODEL, "transport": "video_url(data)", "gt_fingers": GT_FINGERS,
             "multi_image_baseline": MULTI_IMAGE_BASELINE, "results": results},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n증거 기록: {EVIDENCE}")
        return

    # B. 질적 시간변화 묘사
    s2, text2, ttft2, total2 = stream_chat([vid, {"type": "text", "text": TEMPORAL_PROMPT}], max_tokens=512)
    print(f"[B 질적 시간변화] HTTP {s2}  TTFT {ttft2:.2f}s  total {total2:.2f}s")
    print("-" * 60); print(text2); print("-" * 60, "\n")
    results["temporal_qualitative"] = {"status": s2, "ttft_s": ttft2, "total_s": total2, "output": text2}

    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(
        {"model": MODEL, "transport": "video_url(data URL)", "clip": HOST_VIDEO.name,
         "duration_s": 37.16, "gt_fingers": GT_FINGERS,
         "multi_image_baseline": MULTI_IMAGE_BASELINE, "results": results},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"증거 기록: {EVIDENCE}")
    print("\n판정(사용자와): A가 GT 시퀀스를 multi-image보다 살리는가? B가 시간순 변화를 짚는가?")
    print("video_url의 TTFT/total이 frames+audio 대비 어떤가(처리 비용)?")


if __name__ == "__main__":
    main()
