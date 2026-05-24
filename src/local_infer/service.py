"""gje 분석 사이드카 HTTP 서비스 (M4).

GilJob Worker가 탭한 미디어(1fps JPEG + 16kHz PCM)를 턴 단위로 흘려보내면,
SlidingWindowPipeline이 윈도우별 독립 추론으로 per-window 신호를 만들어 반환한다.
**vLLM은 이 서비스 뒤에 숨는다**(성공기준 #4). 집계는 하지 않음 — 신호만 반환(Gemini 몫).

엔드포인트(세션=한 면접 답변 턴):
  POST /sessions/{sid}/start          턴 시작(파이프라인 생성/리셋)
  POST /sessions/{sid}/media {frames,audio,now}  미디어 push + now까지 due 신호 반환
  POST /sessions/{sid}/end   {now}    end-of-turn, tail flush 신호 반환
  GET  /health

프레임/오디오는 base64(GilJob 와이어 포맷 그대로). 신호엔 channel 태그가 붙는다.
"""
from __future__ import annotations

import base64

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .native_eval import WindowEvaluator
from .signals import NonVerbalSignal
from .turn_pipeline import SlidingWindowPipeline


class FrameIn(BaseModel):
    t: float
    jpeg_b64: str


class AudioIn(BaseModel):
    t: float
    pcm_b64: str


class MediaIn(BaseModel):
    frames: list[FrameIn] = []
    audio: list[AudioIn] = []
    now: float


class EndIn(BaseModel):
    now: float


def _sig_dict(s) -> dict:
    channel = "nonverbal" if isinstance(s, NonVerbalSignal) else "evaluation"
    return {"channel": channel, **s.to_dict()}


def create_app(*, evaluator=None, **pipe_kwargs) -> FastAPI:
    """앱 팩토리. evaluator 미지정 시 실제 WindowEvaluator(vLLM)를 lazy 생성.
    테스트는 fake evaluator를 주입해 GPU 없이 HTTP 배관을 검증한다.
    """
    app = FastAPI(title="gje analysis sidecar")
    state: dict = {"evaluator": evaluator, "sessions": {}}

    def get_evaluator():
        if state["evaluator"] is None:
            state["evaluator"] = WindowEvaluator()
        return state["evaluator"]

    def new_session(sid: str) -> dict:
        pending: list = []
        pipe = SlidingWindowPipeline(
            get_evaluator(), on_signal=pending.append, **pipe_kwargs
        )
        sess = {"pipe": pipe, "pending": pending}
        state["sessions"][sid] = sess
        return sess

    def drain(sess: dict) -> list[dict]:
        out = [_sig_dict(s) for s in sess["pending"]]
        sess["pending"].clear()
        return out

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "sessions": len(state["sessions"])}

    @app.post("/sessions/{sid}/start")
    def start(sid: str) -> dict:
        new_session(sid)
        return {"session": sid, "started": True}

    @app.post("/sessions/{sid}/media")
    def media(sid: str, body: MediaIn) -> dict:
        sess = state["sessions"].get(sid) or new_session(sid)
        pipe: SlidingWindowPipeline = sess["pipe"]
        for f in body.frames:
            pipe.add_frame(f.t, base64.b64decode(f.jpeg_b64))
        for a in body.audio:
            pipe.add_audio(a.t, base64.b64decode(a.pcm_b64))
        pipe.poll(body.now)
        return {"session": sid, "signals": drain(sess)}

    @app.post("/sessions/{sid}/end")
    def end(sid: str, body: EndIn) -> dict:
        sess = state["sessions"].get(sid)
        if sess is None:
            raise HTTPException(status_code=404, detail=f"unknown session {sid!r}")
        sess["pipe"].end_turn(body.now)
        signals = drain(sess)
        del state["sessions"][sid]
        return {"session": sid, "signals": signals, "ended": True}

    return app


# uvicorn 진입점: `uvicorn local_infer.service:app`
app = create_app()
