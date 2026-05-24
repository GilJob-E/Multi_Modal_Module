#!/usr/bin/env python3
"""Cold kill-test 스파이크 — periodic prefill thesis 생사 판정.

Phase 3의 "31.5배"는 warm 시점에 최종 오디오를 미리 쥔 best-case였다(정정됨). 여기서는
콘텐츠를 매번 다르게 줘 prefix 캐시 cold를 강제하고, PLAN '## 남은 갭'의 지연 레버
A/B/C를 cold 조건에서 격리 실측한다.

  step1 (cold 바닥 / 레버 C):
      오디오 길이별(5/10/20/30초) end-of-turn TTFT를 격리 측정 — 진짜 baseline이자
      "윈도우를 얼마나 줄이면 단독으로 0.5s에 드나"(레버 C). 프레임 없이 오디오만.
      길이 하나는 두 번 보내 cold→warm 드랍을 확인(prefix 캐시 활성 sanity).

  step2 (레버 A · 핵심):
      [chunk1]을 데운 뒤 [chunk1, chunk2](분리된 audio_url 2파트)를 보내
        (a) chunk1 KV가 히트하는가(자라는 오디오 캐시) — TTFT가 통째 cold 대비 급감하나,
        (b) 청크 분할 eval이 통오디오 eval만큼 일관한가(품질 손상 여부).
      ※ 분리 파트는 각 청크를 독립 인코딩하므로 (a)는 기계적으로 거의 보장된다.
        thesis의 진짜 리스크는 (b) — 분할이 cross-chunk 청각 맥락을 잃어 평가가
        흔들리는지다. 둘 다 기록해 사용자가 판정한다.

  step3 (레버 B):
      tail 청크(1/2/5초) prefill 시간 vs VAD hangover(~500ms). 마지막 청크만 cold일 때
      그 prefill이 침묵窗 안에 들어가 은닉되나. 프레임-warm 한계도 부수 측정(예상 marginal).

실행: PYTHONPATH=src python3 tools/spike_cold_prefill.py --step all
서빙: bash sglang/launch-configs/vllm_e4b_audio.sh  (audio>=2 필요 — step2/3)
종료: docker stop vllm-gemma4-e4b && nvidia-smi
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

from local_infer.native_audio import NativeAudioExtractor, NativeInputAudio

ENDPOINT = "http://localhost:8000/v1/chat/completions"
MODEL = "google/gemma-4-E4B-it"
HOST_VIDEO = Path("/home/kio/workspace/gje/vid_0033.mp4")  # 50.3s fixture (gitignore)
VIDEO_0001 = Path("/home/kio/workspace/gje/vid_0001.mp4")  # 43.5s, 신선 콘텐츠(캐시/사전노출 의심 제거)
EVIDENCE = Path(".sisyphus/evidence/spike-cold-prefill.json")

VAD_HANGOVER_MS = 500.0  # 레버 B 기준선: VAD가 발화 종료를 확정하기까지의 침묵窗

# 분할 vs 통오디오 일관성 비교용 평가 프롬프트(vocal에 prosody를 콕 집음).
EVAL_PROMPT = (
    "다음은 화상 면접 답변의 음성입니다. 청각(vocal) 전달력을 평가하세요: "
    "음량 변화, 말 속도, pause(머뭇거림/공백), 억양의 단조로움/풍부함을 구체적으로 "
    "짚고, 내용(verbal)의 논리·구체성도 함께 평가하세요."
)

_extractor = NativeAudioExtractor()


def window(start_s: float, dur_s: float, video: Path = HOST_VIDEO) -> NativeInputAudio:
    return _extractor.extract_window(video, start_seconds=start_s, duration_seconds=dur_s)


def audio_part(a: NativeInputAudio) -> dict:
    return a.to_content_part()


def frame_part(at_s: float, video: Path = HOST_VIDEO) -> dict:
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-ss", f"{at_s:.3f}", "-i", str(video),
        "-frames:v", "1", "-q:v", "3", "-f", "image2", "pipe:1",
    ]
    out = subprocess.run(cmd, capture_output=True, check=True, timeout=15).stdout
    b64 = base64.b64encode(out).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}


def stream_ttft(content: list[dict], *, max_tokens: int = 16) -> tuple[int, str, float, float]:
    """streaming chat → (status, text, ttft_s, total_s). TTFT = prefill + 첫 디코드 = 사용자 체감 지연."""
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
        return exc.code, exc.read().decode("utf-8", errors="replace"), ttft, time.monotonic() - start


def prime(content: list[dict]) -> float:
    """prefix를 캐시에 태운다(max_tokens=1). 반환 = prime 자체 TTFT(=cold prefill 시간 근사)."""
    _, _, ttft, _ = stream_ttft(content, max_tokens=1)
    return ttft


# 매 요청 콘텐츠를 다르게 줘 cold를 강제하기 위한 distinct 윈도우 (50.3s fixture 내).
TXT = {"type": "text", "text": "이 음성을 평가용으로 들어주세요."}


def step1_cold_floor() -> dict:
    print("\n=== STEP 1: cold 바닥 / 레버 C — 오디오 길이별 end-of-turn TTFT ===")
    # (length_s, start_s) — start를 다르게 줘 각 blob을 unique=cold로 만든다.
    specs = [(5.0, 0.0), (10.0, 6.0), (20.0, 16.0), (30.0, 20.0)]
    rows = []
    for dur, start in specs:
        a = window(start, dur)
        status, _, ttft, total = stream_ttft([audio_part(a), TXT])
        print(f"  {dur:>4.0f}s @ {start:>4.0f}s : HTTP {status}  TTFT {ttft:6.3f}s  total {total:6.3f}s"
              + ("  ✓<0.5s" if 0 <= ttft < 0.5 else ""))
        rows.append({"dur_s": dur, "start_s": start, "status": status, "ttft_s": ttft, "total_s": total})
    # cold→warm sanity: 10s를 재전송(동일 콘텐츠) → 캐시 히트로 TTFT 급감해야 prefix 캐시 활성.
    a = window(6.0, 10.0)
    _, _, ttft_cold2, _ = stream_ttft([audio_part(a), TXT])
    _, _, ttft_warm, _ = stream_ttft([audio_part(a), TXT])
    print(f"  [sanity] 10s 동일 재전송: cold {ttft_cold2:.3f}s → warm {ttft_warm:.3f}s "
          f"(drop {ttft_cold2 - ttft_warm:+.3f}s) — prefix 캐시 {'활성' if ttft_warm < ttft_cold2 * 0.7 else '의심'}")
    return {
        "sweep": rows,
        "cache_sanity_10s": {"cold_s": ttft_cold2, "warm_s": ttft_warm},
    }


def step2_lever_a() -> dict:
    print("\n=== STEP 2: 레버 A (핵심) — 자라는 오디오 KV 히트 + 청크 vs 통오디오 일관성 ===")
    chunk1 = window(0.0, 10.0)   # 0-10
    chunk2 = window(10.0, 10.0)  # 10-20
    whole = window(0.0, 20.0)    # 0-20 통오디오
    cp1 = window(30.0, 10.0)     # 30-40  (한 번도 안 데운 cold pair)
    cp2 = window(40.0, 10.0)     # 40-50

    # (a) KV 히트: chunk1 데운 뒤 [chunk1, chunk2]가 통째-cold 대비 급감하나
    c1_cold = prime([audio_part(chunk1), TXT])                 # 10s cold prefill 기준
    prime([audio_part(chunk1), TXT])                           # chunk1 prefix를 캐시에 태움
    _, _, grow_ttft, _ = stream_ttft([audio_part(chunk1), audio_part(chunk2), TXT])
    _, _, coldpair_ttft, _ = stream_ttft([audio_part(cp1), audio_part(cp2), TXT])  # 20s 통째 cold(2파트)
    hit = grow_ttft < coldpair_ttft * 0.7
    print(f"  chunk1 cold prefill(10s)      : {c1_cold:6.3f}s")
    print(f"  [chunk1*, chunk2] grow TTFT   : {grow_ttft:6.3f}s   (chunk1 데운 뒤)")
    print(f"  [cp1, cp2] cold pair TTFT(20s): {coldpair_ttft:6.3f}s")
    print(f"  → chunk1 KV 히트: {'YES' if hit else 'NO'} "
          f"(grow가 cold pair의 {grow_ttft / coldpair_ttft * 100:.0f}%; "
          f"히트면 ≈ chunk2 단독 prefill ~{c1_cold:.2f}s)")

    # (b) 일관성: 분할 2파트 eval vs 통오디오 1파트 eval — 같은 20s를 평가하는데 흔들리나
    _, eval_chunked, ce_ttft, _ = stream_ttft(
        [audio_part(chunk1), audio_part(chunk2), {"type": "text", "text": EVAL_PROMPT}], max_tokens=512)
    _, eval_whole, we_ttft, _ = stream_ttft(
        [audio_part(whole), {"type": "text", "text": EVAL_PROMPT}], max_tokens=512)
    print(f"\n  --- 분할 2파트 eval (TTFT {ce_ttft:.2f}s) ---\n{eval_chunked}")
    print(f"\n  --- 통오디오 1파트 eval (TTFT {we_ttft:.2f}s) ---\n{eval_whole}")
    print("\n  → 일관성 판정(사용자): 두 평가가 같은 음성을 동일하게 짚는가, 분할이 prosody/맥락을 잃는가?")

    return {
        "kv_hit": {
            "chunk1_cold_prefill_s": c1_cold,
            "grow_ttft_s": grow_ttft,
            "coldpair_ttft_s": coldpair_ttft,
            "hit_detected": hit,
        },
        "consistency": {
            "chunked_2part": {"ttft_s": ce_ttft, "output": eval_chunked},
            "whole_1part": {"ttft_s": we_ttft, "output": eval_whole},
            "verdict": "사용자 육안 판정 필요(분할 vs 통오디오 평가 일치성)",
        },
    }


def step3_lever_b() -> dict:
    print("\n=== STEP 3: 레버 B — tail 청크 prefill vs VAD hangover(%.0fms) ===" % VAD_HANGOVER_MS)
    rows = []
    for dur, start in [(1.0, 5.0), (2.0, 12.0), (5.0, 25.0)]:
        a = window(start, dur)
        pf = prime([audio_part(a), TXT])  # tail만 cold일 때 prefill 시간
        hidden = pf * 1000.0 <= VAD_HANGOVER_MS
        print(f"  tail {dur:>3.0f}s prefill: {pf * 1000:7.1f}ms  "
              f"{'≤ hangover → 은닉 가능' if hidden else '> hangover → 노출'}")
        rows.append({"tail_s": dur, "prefill_ms": pf * 1000.0, "hidden_in_hangover": hidden})
    # 부수: 프레임 3장 warm 한계(예상 marginal)
    frames = [frame_part(t) for t in (3.0, 10.0, 17.0)]
    pf_frames = prime(frames + [TXT])
    print(f"  [부수] 프레임 3장 prefill: {pf_frames * 1000:.1f}ms (예상 marginal)")
    return {"hangover_ms": VAD_HANGOVER_MS, "tails": rows, "frames3_prefill_ms": pf_frames * 1000.0}


def step_confirm() -> dict:
    """확증 — STEP 1 'cold가 싸다' 주장의 3대 미지수를 신선 vid_0001로 직접 검증.

    미지수1·2: 서로 다른 30s 클립을 연속 발사 → 턴1(부팅 cold)만 비싸고 턴2..N(전부 unique
      = 캐시 미스)이 ~0.1s로 유지되면 'per-turn cold가 싸다'가 방탄. 턴1은 선warm 대상(부팅
      더미)이고, 턴2가 곧 '선warm 후 첫 실제 턴'이다.
    미지수3: 라이브 경로 VAD→ffmpeg 컷→base64→POST의 클라이언트측 비용(추출+인코딩)을 재서
      서버 TTFT에 더한 end-to-end 지연을 본다(스파이크는 그동안 WAV를 미리 잘라놔 누락했던 부분).
    """
    print("\n=== CONFIRM: 신선 vid_0001로 cold steady-state + e2e 검증 ===")
    # 서로 다른 30s 클립들(겹쳐도 시작 offset이 달라 바이트=토큰이 unique → 캐시 미스=cold).
    # 턴1을 vid_0001@0으로 둬 '부팅 후 첫 턴'을 그대로 노출.
    specs = [
        (VIDEO_0001, 0.0, "vid_0001@0  (부팅 첫 턴)"),
        (VIDEO_0001, 7.0, "vid_0001@7"),
        (VIDEO_0001, 13.0, "vid_0001@13"),
        (HOST_VIDEO, 0.0, "vid_0033@0"),
        (HOST_VIDEO, 10.0, "vid_0033@10"),
        (HOST_VIDEO, 20.0, "vid_0033@20"),
    ]
    rows = []
    for i, (vid, start, label) in enumerate(specs, 1):
        t0 = time.monotonic()
        a = window(start, 30.0, video=vid)        # 클라이언트측: ffmpeg 컷 + base64
        t_extract = time.monotonic() - t0
        status, _, ttft, total = stream_ttft([audio_part(a), TXT])  # 서버측: end-of-turn TTFT
        e2e = t_extract + ttft
        note = "← 부팅 워밍업" if i == 1 else ("✓ e2e<0.5s" if 0 <= e2e < 0.5 else "")
        print(f"  턴{i} {label:<26}: 추출 {t_extract*1000:6.1f}ms + TTFT {ttft:6.3f}s = e2e {e2e:6.3f}s {note}")
        rows.append({"turn": i, "label": label, "extract_ms": t_extract * 1000.0,
                     "ttft_s": ttft, "total_s": total, "e2e_s": e2e, "status": status})
    steady = [r for r in rows if r["turn"] >= 2]
    steady_max = max(r["e2e_s"] for r in steady)
    print(f"\n  턴1(부팅): e2e {rows[0]['e2e_s']:.3f}s  |  턴2..N(선warm 후, 전부 unique cold) e2e 최대 {steady_max:.3f}s")
    print(f"  → 'per-turn cold 싸다' {'확증' if steady_max < 0.5 else '반증'}: 신선 콘텐츠로도 턴2부터 < 0.5s {'성립' if steady_max < 0.5 else '불성립'}")

    # 미지수와 별개: 사용자에게 보여줄 — 신선 vid_0001에 full 루브릭 평가(프레임+오디오) 실제 답변
    print("\n  --- 모델 답변 (신선 vid_0001 30s @0, 프레임3 + 오디오 full 루브릭) ---")
    frames = [frame_part(t, video=VIDEO_0001) for t in (3.0, 15.0, 27.0)]
    av = window(0.0, 30.0, video=VIDEO_0001)
    _, eval_text, e_ttft, e_total = stream_ttft(
        frames + [audio_part(av), {"type": "text", "text": EVAL_PROMPT}], max_tokens=768)
    print(f"  (TTFT {e_ttft:.2f}s, total {e_total:.2f}s)\n{eval_text}")

    return {
        "steady_state": {"turns": rows, "steady_max_e2e_s": steady_max,
                         "boot_turn_e2e_s": rows[0]["e2e_s"]},
        "fresh_eval_vid0001": {"ttft_s": e_ttft, "total_s": e_total, "output": eval_text},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", choices=["1", "2", "3", "confirm", "all"], default="all")
    args = parser.parse_args()

    # health
    try:
        with urllib.request.urlopen("http://localhost:8000/v1/models", timeout=5) as r:
            ready = MODEL in r.read().decode("utf-8")
        print(f"서빙 ready: {ready}")
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"vLLM 미기동: {exc}\n  bash sglang/launch-configs/vllm_e4b_audio.sh 먼저 실행")

    results: dict = {"model": MODEL, "vad_hangover_ms": VAD_HANGOVER_MS}
    if args.step in ("1", "all"):
        results["step1_cold_floor"] = step1_cold_floor()
    if args.step in ("2", "all"):
        results["step2_lever_a"] = step2_lever_a()
    if args.step in ("3", "all"):
        results["step3_lever_b"] = step3_lever_b()
    if args.step in ("confirm", "all"):
        results["confirm"] = step_confirm()

    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n증거 기록: {EVIDENCE}")
    print("\n판정(결정규칙, PLAN '## 남은 갭'):")
    print("  레버 A 히트 AND 청크 eval 일관 → periodic prefill viable (청크 스트리밍 워밍으로 재설계).")
    print("  레버 A 미스 OR 일관성 깨짐 → 오디오 통째 cold; 레버 B+C 조합으로 갈 수 있나 판정.")


if __name__ == "__main__":
    main()
