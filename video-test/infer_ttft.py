import base64
import json
import sys
import time

import requests

video_path = sys.argv[1] if len(sys.argv) > 1 else "sample30.mp4"
with open(video_path, "rb") as f:
    b64 = base64.b64encode(f.read()).decode()

payload = {
    "model": "google/gemma-4-31B-it",
    "stream": True,
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "video_url",
                    "video_url": {"url": f"data:video/mp4;base64,{b64}"},
                },
                {
                    "type": "text",
                    "text": "이 비디오에서 일어나는 일을 시간 순서대로 한국어로 자세히 설명해줘.",
                },
            ],
        }
    ],
    "max_tokens": 256,
    "temperature": 0.2,
}

t0 = time.time()
r = requests.post(
    "http://localhost:8000/v1/chat/completions",
    json=payload,
    stream=True,
    timeout=300,
)
ttft = None
n_tokens = 0
last_t = t0
first_chars = []

for raw in r.iter_lines():
    if not raw:
        continue
    if not raw.startswith(b"data: "):
        continue
    body = raw[6:]
    if body == b"[DONE]":
        break
    chunk = json.loads(body)
    delta = chunk["choices"][0].get("delta", {})
    content = delta.get("content")
    if content is None:
        continue
    now = time.time()
    if ttft is None:
        ttft = now - t0
    n_tokens += 1
    last_t = now
    if len(first_chars) < 5:
        first_chars.append(content)

total = last_t - t0
gen_time = total - (ttft or 0)
tps = n_tokens / gen_time if gen_time > 0 else 0
print(f"TTFT: {ttft:.3f}s")
print(f"total: {total:.3f}s, output_chunks: {n_tokens}")
print(f"generation TPS (chunks/s): {tps:.2f}")
print(f"first chunks: {first_chars}")
