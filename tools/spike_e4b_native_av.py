#!/usr/bin/env python3
"""Phase 1 검증 스파이크 — Gemma 4 E4B native AV 재검증.

목적: 이전 audio "no-go"가 모델 천장이 아니라 payload 버그(input_audio 대신 audio_url)였음을
실측 확인하고, E4B의 평가 깊이·prosody 묘사·지연을 측정해 아키텍처 (1)단일 E4B vs (2)2-스테이지를 가른다.

  smoke : 오디오 단독 전사로 audio_url payload 자체를 격리 검증(가장 싼 GO/NO-GO kill).
  full  : ≤30초 윈도우로 AV전송 방식·품질 루브릭·prosody·지연 측정 (smoke 통과 후).

실행: PYTHONPATH=src python3 tools/spike_e4b_native_av.py --mode smoke
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from local_infer.native_audio import NativeAudioExtractor

ENDPOINT = "http://localhost:8000/v1/chat/completions"
MODEL = "google/gemma-4-E4B-it"
HOST_VIDEO = Path("/home/kio/workspace/gje/vid_0033.mp4")
EVIDENCE = Path(".sisyphus/evidence/spike-e4b-native-av.json")

# 면접 답변 종합 평가 프롬프트. verbal/vocal/visual 세 축을 명시적으로 요구하고
# vocal 안에 prosody(음량·속도·pause·억양)를 콕 집어 묘사를 강제 → 전사만 하는지 판별.
EVAL_PROMPT = (
    "다음은 화상 면접에서 한 지원자의 답변입니다(프레임 이미지 + 음성). "
    "면접관 관점에서 아래 세 축으로 종합 평가하세요.\n"
    "1) 언어(verbal): 답변 내용의 논리·구조·구체성.\n"
    "2) 청각(vocal): 전달력 — 특히 음량 변화, 말 속도, pause(머뭇거림/공백), "
    "억양이 단조로운지 풍부한지 구체적으로 짚어주세요.\n"
    "3) 시각(visual): 표정·시선·자세 등 비언어 단서.\n"
    "각 축마다 관찰한 근거와 개선점을 함께 적으세요."
)
PROSODY_PROBE = (
    "이 음성의 prosody만 집중해서 묘사하세요: 음량의 크기와 변화, 말하는 속도, "
    "중간 pause나 머뭇거림, 억양이 단조로운지 변화가 있는지. 전사하지 말고 청각적 특징만."
)


def post_chat(content: list[dict], *, max_tokens: int = 256) -> tuple[int, str, float, float]:
    """non-stream chat 요청 → (status, text, ttfb_s, total_s). 실패해도 본문/상태 반환."""
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "stream": False,
    }
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = resp.read().decode("utf-8")
            total = time.monotonic() - start
            data = json.loads(body)
            text = data["choices"][0]["message"]["content"]
            return resp.status, text, total, total
    except urllib.error.HTTPError as exc:
        total = time.monotonic() - start
        return exc.code, exc.read().decode("utf-8", errors="replace"), total, total


def extract_frame(video: Path, at_seconds: float) -> dict:
    """ffmpeg로 한 프레임을 jpeg 추출 → image_url data URL content part."""
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-ss", f"{at_seconds:.3f}", "-i", str(video),
        "-frames:v", "1", "-q:v", "3", "-f", "image2", "pipe:1",
    ]
    out = subprocess.run(cmd, capture_output=True, check=True, timeout=15).stdout
    b64 = base64.b64encode(out).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}


def stream_chat(content: list[dict], *, max_tokens: int = 512) -> tuple[int, str, float, float]:
    """streaming chat → (status, text, ttft_s, total_s). TTFT = 첫 토큰까지."""
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


def run_full() -> None:
    print("=== FULL: 프레임(image_url) + audio_url native AV 평가 배터리 ===")
    window_start, window_dur = 0.0, 20.0
    frames = [extract_frame(HOST_VIDEO, t) for t in (3.0, 10.0, 17.0)]
    audio = NativeAudioExtractor().extract_window(
        HOST_VIDEO, start_seconds=window_start, duration_seconds=window_dur
    )
    print(f"입력: 프레임 {len(frames)}장(@3/10/17s) + 오디오 {window_dur:g}s(@{window_start:g}s)\n")

    results = {}

    # ② 품질 루브릭 + ③ prosody (한 평가 프롬프트가 vocal 안에서 prosody 강제) + ④ 지연
    eval_content = frames + [audio.to_content_part(), {"type": "text", "text": EVAL_PROMPT}]
    status, text, ttft, total = stream_chat(eval_content, max_tokens=768)
    print(f"[평가 루브릭] HTTP {status}  TTFT {ttft:.2f}s  total {total:.2f}s")
    print("-" * 60); print(text); print("-" * 60, "\n")
    results["quality_rubric"] = {"status": status, "ttft_s": ttft, "total_s": total, "output": text}

    # ③ prosody 격리 프로브 (오디오만, 전사 금지)
    prosody_content = [audio.to_content_part(), {"type": "text", "text": PROSODY_PROBE}]
    p_status, p_text, p_ttft, p_total = stream_chat(prosody_content, max_tokens=384)
    print(f"[prosody 격리] HTTP {p_status}  TTFT {p_ttft:.2f}s  total {p_total:.2f}s")
    print("-" * 60); print(p_text); print("-" * 60, "\n")
    results["prosody_probe"] = {"status": p_status, "ttft_s": p_ttft, "total_s": p_total, "output": p_text}

    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(
        json.dumps(
            {
                "model": MODEL,
                "transport": "image_url frames(3) + audio_url",
                "window": {"start_s": window_start, "dur_s": window_dur, "frames_at_s": [3, 10, 17]},
                "results": results,
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"증거 기록: {EVIDENCE}")
    print("\n판정(사용자와 함께): 위 평가가 예시 수준의 깊이인가? prosody를 실제 묘사하는가, 전사만 하는가?")


def run_smoke() -> None:
    print("=== SMOKE: 오디오 단독 전사 (audio_url payload 격리 검증) ===")
    audio = NativeAudioExtractor().extract_window(HOST_VIDEO, start_seconds=0.0, duration_seconds=20.0)
    content = [
        audio.to_content_part(),
        {"type": "text", "text": "이 오디오에 들리는 한국어 발화를 그대로 전사해줘."},
    ]
    status, text, _, total = post_chat(content)
    print(f"HTTP {status}  ({total:.2f}s)")
    print("-" * 60)
    print(text)
    print("-" * 60)
    if status == 200:
        print("GO: audio_url payload가 HTTP 200으로 처리됨. 위 전사가 실제 발화와 일치하는지 육안 확인.")
    else:
        print("NO-GO: payload/extras/30초 캡을 점검하라 (이전 no-go 재현 여부).")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["smoke", "full"], default="smoke")
    args = parser.parse_args()
    if args.mode == "smoke":
        run_smoke()
    else:
        run_full()


if __name__ == "__main__":
    main()
