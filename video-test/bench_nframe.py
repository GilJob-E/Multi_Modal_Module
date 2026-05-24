#!/usr/bin/env python3
"""
A방식(누적 프레임) N-frame TTFT/TPS 벤치.
실시간 화상통화: 1fps로 프레임 누적 → image_url 다중 + text → 스트리밍 텍스트.
고정 시스템 프롬프트(prefix)로 prefix-cache hit 효과까지 측정.

usage: python3 bench_nframe.py [frames_dir] [base_url]
"""
import base64, json, os, sys, time, glob
import requests

FRAMES_DIR = sys.argv[1] if len(sys.argv) > 1 else "frames"
BASE = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8000"
MODEL = "google/gemma-4-31B-it"

# 고정 시스템 프롬프트 = prefix cache 대상 (면접관 페르소나 축약본)
SYSTEM = (
    "당신은 한국어 화상 면접관입니다. 지원자의 영상 프레임이 1초 간격으로 누적 전달됩니다. "
    "표정·자세의 변화를 관찰하고, 차분하게 한 번에 한 질문씩 진행하세요. 한국어로만 답하세요."
)
PROMPT = "지금 지원자의 표정과 자세를 한 문장으로 묘사하고, 자연스러운 후속 질문 한 개를 던지세요."

def load_frames(n):
    files = sorted(glob.glob(os.path.join(FRAMES_DIR, "*.jpg")))[:n]
    out = []
    for f in files:
        with open(f, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()
        out.append(f"data:image/jpeg;base64,{b64}")
    return out, sum(os.path.getsize(f) for f in files)

def build_messages(frame_urls):
    content = [{"type": "image_url", "image_url": {"url": u}} for u in frame_urls]
    content.append({"type": "text", "text": PROMPT})
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": content},
    ]

def run_once(n_frames, max_tokens=128):
    frame_urls, raw_bytes = load_frames(n_frames)
    payload = {
        "model": MODEL, "stream": True, "messages": build_messages(frame_urls),
        "max_tokens": max_tokens, "temperature": 0.2,
    }
    t0 = time.time()
    r = requests.post(f"{BASE}/v1/chat/completions", json=payload, stream=True, timeout=300)
    ttft = None; n_tok = 0; last = t0
    for raw in r.iter_lines():
        if not raw or not raw.startswith(b"data: "):
            continue
        body = raw[6:]
        if body == b"[DONE]":
            break
        try:
            delta = json.loads(body)["choices"][0].get("delta", {})
        except Exception:
            continue
        if delta.get("content") is None:
            continue
        now = time.time()
        if ttft is None:
            ttft = now - t0
        n_tok += 1; last = now
    total = last - t0
    gen = total - (ttft or 0)
    tps = n_tok / gen if gen > 0 else 0
    return {"n_frames": n_frames, "raw_kb": round(raw_bytes/1024,1),
            "ttft_s": round(ttft or 0,3), "total_s": round(total,3),
            "out_chunks": n_tok, "tps": round(tps,1)}

def main():
    print(f"frames_dir={FRAMES_DIR} base={BASE}")
    print(f"available frames: {len(glob.glob(os.path.join(FRAMES_DIR,'*.jpg')))}")
    print("="*78)
    results = []
    for n in [1, 3, 5, 10]:
        # cold (첫 호출), warm (prefix cache hit 기대 — 같은 system+frames 재전송)
        cold = run_once(n); time.sleep(0.5)
        warm = run_once(n)
        print(f"N={n:2d} | raw {cold['raw_kb']:6.1f}KB | "
              f"COLD ttft {cold['ttft_s']:.3f}s tps {cold['tps']:5.1f} | "
              f"WARM ttft {warm['ttft_s']:.3f}s tps {warm['tps']:5.1f} | "
              f"out {cold['out_chunks']}/{warm['out_chunks']}")
        results.append({"n": n, "cold": cold, "warm": warm})
    print("="*78)
    print(json.dumps(results, ensure_ascii=False))

if __name__ == "__main__":
    main()
