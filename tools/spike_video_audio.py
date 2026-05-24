#!/usr/bin/env python3
"""video_url 단독 → 오디오까지 native로 듣는가? (load_audio_from_video 실측)

별도 audio_url 없이 video_url 하나만 보내고 전사를 시킨다.
- 전사가 실제 발화와 일치 → 오디오가 비디오에서 native 로드됨(아키텍처 단순화 신호).
- "오디오 없음/못 들음" → vLLM video_url은 시각 전용, 여전히 audio_url 별도 필요.

클립: /tmp/clip_av_28s.mp4 (vid_0001 0-28s, 16kHz mono aac, 음성 유지).
실행: python3 tools/spike_video_audio.py
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
CLIP = Path("/tmp/clip_av_28s.mp4")
EVIDENCE = Path(".sisyphus/evidence/spike-video-audio.json")

TRANSCRIBE = (
    "This is a video of a person speaking. Transcribe exactly the words the person says "
    "in the audio track, verbatim. If you cannot hear any audio, say exactly 'NO AUDIO'."
)
PROSODY = (
    "Listen to the audio of this video and describe the speaker's vocal delivery: volume, "
    "speaking pace, pauses/hesitations, and whether the intonation is monotone or varied. "
    "Do not transcribe the words — describe the sound only."
)


def stream_chat(content: list[dict], *, max_tokens: int = 512) -> tuple[int, str, float, float]:
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens, "temperature": 0.0, "stream": True,
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
        return exc.code, exc.read().decode("utf-8", errors="replace"), ttft, time.monotonic() - start


def video_part() -> dict:
    b64 = base64.b64encode(CLIP.read_bytes()).decode("ascii")
    return {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{b64}"}}


def main() -> None:
    print(f"=== video_url 단독 → native audio? ({CLIP.name}, 28s, 음성 포함) ===\n")
    vid = video_part()
    print(f"video data URL: {len(vid['video_url']['url'])/1024:.0f} KB\n")
    results = {}

    s, text, ttft, total = stream_chat([vid, {"type": "text", "text": TRANSCRIBE}], max_tokens=512)
    print(f"[전사] HTTP {s}  TTFT {ttft:.2f}s  total {total:.2f}s")
    print("-" * 60); print(text); print("-" * 60)
    verdict = "NO AUDIO" not in text.upper() and s == 200 and len(text.strip()) > 10
    print(f"→ 오디오 native 로드 추정: {'YES (전사 산출)' if verdict else 'NO/불명'}\n")
    results["transcribe"] = {"status": s, "ttft_s": ttft, "total_s": total, "output": text}

    if verdict:
        s2, text2, ttft2, total2 = stream_chat([vid, {"type": "text", "text": PROSODY}], max_tokens=384)
        print(f"[prosody] HTTP {s2}  TTFT {ttft2:.2f}s  total {total2:.2f}s")
        print("-" * 60); print(text2); print("-" * 60, "\n")
        results["prosody"] = {"status": s2, "ttft_s": ttft2, "total_s": total2, "output": text2}

    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(
        {"model": MODEL, "transport": "video_url(data URL) ONLY — no separate audio_url",
         "clip": "vid_0001 0-28s, 16kHz mono", "audio_native_loaded": verdict, "results": results},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"증거 기록: {EVIDENCE}")
    print("\n판정(사용자와): 전사가 실제 발화와 일치하는가? video_url 하나로 AV 동시 = 아키텍처 단순화.")


if __name__ == "__main__":
    main()
