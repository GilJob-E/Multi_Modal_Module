#!/usr/bin/env python3
"""Phase 3 하니스 — vid_0033으로 턴 단위 native AV 평가 + periodic prefill 효과 측정.

NativeInterviewEvaluator를 vid_0033 프레임·오디오로 구동해 ① 평가 품질(verbal/vocal/visual)
회귀가 없는지 ② periodic prefill이 end-of-turn TTFT를 줄이는지를 정량 측정한다.

측정 격리: warm-off와 warm-on은 서로 다른 프레임셋을 써서 콘텐츠 토큰이 달라지게 한다
(vLLM prefix 캐시는 session_id가 아니라 토큰 내용으로 히트하므로, 같은 콘텐츠를 쓰면
warm-off의 평가가 캐시를 채워 warm-on 비교가 오염된다).
  warm-off : 콜드 prefix로 바로 evaluate → 콜드 멀티모달 prefill TTFT.
  warm-on  : 다른 콘텐츠를 push + warm(periodic prefill 대표) 후 evaluate → 워밍된 TTFT.

실행: PYTHONPATH=src uv run --with requests python3 tools/turn_pipeline_demo.py
"""
from __future__ import annotations

import base64
import json
import subprocess
import time
from pathlib import Path

from local_infer.native_audio import NativeAudioExtractor
from local_infer.native_eval import NativeInterviewEvaluator

HOST_VIDEO = Path("/home/kio/workspace/gje/vid_0033.mp4")
EVIDENCE = Path(".sisyphus/evidence/phase3-prefill-effect.json")
AUDIO_START, AUDIO_DUR = 0.0, 20.0
OFF_FRAMES = (3.0, 10.0, 17.0)   # 콜드 baseline
ON_FRAMES = (5.0, 12.0, 19.0)    # 다른 프레임 → 캐시 격리


def extract_frame_b64(video: Path, at_seconds: float) -> str:
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-ss", f"{at_seconds:.3f}", "-i", str(video),
        "-frames:v", "1", "-q:v", "3", "-f", "image2", "pipe:1",
    ]
    out = subprocess.run(cmd, capture_output=True, check=True, timeout=15).stdout
    return base64.b64encode(out).decode("ascii")


def push_turn(evaluator: NativeInterviewEvaluator, session_id: str, frame_times) -> None:
    """한 턴 분량의 프레임·오디오를 evaluator에 push."""
    for t in frame_times:
        evaluator.add_frame(session_id, int(t * 1000), extract_frame_b64(HOST_VIDEO, t))
    audio = NativeAudioExtractor().extract_window(
        HOST_VIDEO, start_seconds=AUDIO_START, duration_seconds=AUDIO_DUR
    )
    evaluator.set_audio_window(session_id, audio)


def eval_timed(evaluator: NativeInterviewEvaluator, session_id: str) -> tuple[float, float, str]:
    """evaluate를 소비하며 (ttft_s, total_s, text) 측정."""
    t0 = time.monotonic()
    ttft = -1.0
    chunks: list[str] = []
    for tok in evaluator.evaluate(session_id):
        if ttft < 0:
            ttft = time.monotonic() - t0
        chunks.append(tok)
    return ttft, time.monotonic() - t0, "".join(chunks)


def main() -> None:
    evaluator = NativeInterviewEvaluator()
    evaluator.client.health()  # E4B ready 확인 (실패 시 예외)

    # (A) warm-off: 콜드 prefix로 바로 평가
    push_turn(evaluator, "off", OFF_FRAMES)
    off_ttft, off_total, text = eval_timed(evaluator, "off")
    print(f"[warm-off] end-of-turn TTFT {off_ttft:.3f}s  total {off_total:.2f}s")

    # (B) warm-on: 다른 콘텐츠 push → warm(periodic prefill 대표) → 평가
    push_turn(evaluator, "on", ON_FRAMES)
    evaluator.warm("on")
    on_ttft, on_total, _ = eval_timed(evaluator, "on")
    print(f"[warm-on ] end-of-turn TTFT {on_ttft:.3f}s  total {on_total:.2f}s")

    speedup = off_ttft / on_ttft if on_ttft > 0 else float("inf")
    print(f"\nperiodic prefill TTFT 단축: {off_ttft:.3f}s → {on_ttft:.3f}s ({speedup:.1f}x)")
    print("\n=== 평가 출력 (warm-off 세션, 품질 회귀 육안 확인용) ===")
    print(text)

    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(
        json.dumps(
            {
                "transport": "image_url frames(3) + audio_url",
                "audio_window": {"start_s": AUDIO_START, "dur_s": AUDIO_DUR},
                "warm_off": {"frames_at_s": list(OFF_FRAMES), "ttft_s": off_ttft, "total_s": off_total},
                "warm_on": {"frames_at_s": list(ON_FRAMES), "ttft_s": on_ttft, "total_s": on_total},
                "ttft_speedup_x": speedup,
                "eval_output_sample": text,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n증거 기록: {EVIDENCE}")


if __name__ == "__main__":
    main()
