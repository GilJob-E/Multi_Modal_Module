#!/usr/bin/env python3
"""HTTP 서비스 배관 테스트 — TestClient + fake evaluator(GPU 불필요).

start/media/end 흐름, base64 디코드, per-window 신호 반환 + channel 태그를 본다.
실제 추론은 M5 e2e에서. 실행: .venv/bin/python tests/test_service.py
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fastapi.testclient import TestClient  # noqa: E402

from local_infer.service import create_app  # noqa: E402
from local_infer.signals import EvaluationSignal, NonVerbalSignal  # noqa: E402


class FakeEvaluator:
    def __init__(self) -> None:
        self.nv = 0
        self.ev = 0

    def read_nonverbal(self, frames, pcm, *, t, window_s, src_fps=1.0, sample_rate=16000):
        self.nv += 1
        assert all(isinstance(f, bytes) for f in frames), "프레임 base64 디코드 실패"
        return NonVerbalSignal(t=t, window_s=window_s, state="engaged", intensity=0.6, note="n")

    def evaluate_window(self, frames, pcm, *, window_start_s, window_dur_s, src_fps=1.0, sample_rate=16000):
        self.ev += 1
        assert isinstance(pcm, bytes) and pcm, "pcm base64 디코드 실패"
        return EvaluationSignal(window_start_s=window_start_s, window_dur_s=window_dur_s,
                                verbal={"logic": "ok"}, vocal={}, visual={}, key_observations=["x"])


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def test_full_turn_flow():
    fake = FakeEvaluator()
    client = TestClient(create_app(evaluator=fake, nonverbal_window_s=3.0, eval_window_s=16.0))

    assert client.get("/health").json()["ok"] is True
    sid = "turn1"
    assert client.post(f"/sessions/{sid}/start").json()["started"] is True

    # 0~6초 미디어 push → 비언어 2개([0,3),[3,6))
    frames = [{"t": i + 0.5, "jpeg_b64": _b64(b"\xff\xd8jpeg")} for i in range(6)]
    audio = [{"t": float(i), "pcm_b64": _b64(b"\x00\x00" * 16000)} for i in range(6)]
    r = client.post(f"/sessions/{sid}/media", json={"frames": frames, "audio": audio, "now": 6.0}).json()
    sigs = r["signals"]
    print(f"  media@6: {len(sigs)} signals, channels={[s['channel'] for s in sigs]}")
    assert len(sigs) == 2 and all(s["channel"] == "nonverbal" for s in sigs)
    assert all("state" in s for s in sigs)

    # 6~16초 추가 → now=16에서 평가 윈도우 1개([0,16)) + 비언어 더
    frames2 = [{"t": i + 0.5, "jpeg_b64": _b64(b"\xff\xd8jpeg")} for i in range(6, 16)]
    audio2 = [{"t": float(i), "pcm_b64": _b64(b"\x00\x00" * 16000)} for i in range(6, 16)]
    r2 = client.post(f"/sessions/{sid}/media", json={"frames": frames2, "audio": audio2, "now": 16.0}).json()
    chans2 = [s["channel"] for s in r2["signals"]]
    print(f"  media@16: channels={chans2}")
    assert "evaluation" in chans2, chans2
    ev_sig = next(s for s in r2["signals"] if s["channel"] == "evaluation")
    assert ev_sig["verbal"] == {"logic": "ok"} and ev_sig["window_dur_s"] == 16.0

    # end-of-turn flush
    r3 = client.post(f"/sessions/{sid}/end", json={"now": 18.0}).json()
    print(f"  end@18: ended={r3['ended']} tail signals={len(r3['signals'])}")
    assert r3["ended"] is True
    # 세션 제거 확인
    assert client.post(f"/sessions/{sid}/end", json={"now": 19.0}).status_code == 404

    assert fake.nv >= 6 and fake.ev >= 1, (fake.nv, fake.ev)
    print(f"  ✓ full turn flow (fake nv={fake.nv} eval={fake.ev}, 신호 배관·base64·channel 태그 OK)")


def main() -> int:
    print("=== service tests (1) ===")
    try:
        test_full_turn_flow()
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print(f"=== FAILED: {e} ===")
        return 1
    print("=== ALL PASS ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
