import base64
import sys
import requests

video_path = sys.argv[1] if len(sys.argv) > 1 else "sample30.mp4"
with open(video_path, "rb") as f:
    b64 = base64.b64encode(f.read()).decode()

r = requests.post(
    "http://localhost:8000/v1/chat/completions",
    json={
        "model": "google/gemma-4-31B-it",
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
                        "text": (
                            "이 비디오에서 일어나는 일을 시간 순서대로 한국어로 자세히 설명해줘. "
                            "인물·물체·동작·분위기를 모두 포함해. 반드시 한국어로 답해."
                        ),
                    },
                ],
            }
        ],
        "max_tokens": 1024,
        "temperature": 0.2,
    },
    timeout=300,
)

print(r.json()["choices"][0]["message"]["content"])
