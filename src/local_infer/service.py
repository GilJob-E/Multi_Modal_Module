"""gje 분석 사이드카 HTTP 서비스 (M4).

GilJob Worker가 탭한 미디어(1fps JPEG + 16kHz PCM)를 턴 단위로 흘려보내면,
SlidingWindowPipeline이 윈도우별 **백그라운드** 독립 추론으로 per-window 신호를 만든다.
poll/add_*는 즉시 반환하고 추론은 워커 스레드에서 돌아, 채널①(저지연 아바타 반응)이
채널②(무거운 평가) 뒤에 막히지 않는다. end_turn은 답변 마지막 구간만 compact 평가해
turn 종료 지연을 묶는다(체감 레이턴시 ≤목표). **vLLM은 이 서비스 뒤에 숨는다**(성공기준 #4).
집계는 하지 않음 — 신호만 반환(Gemini 몫).

실행기는 **앱 레벨에서 공유**(세션마다 만들지 않음 → 스레드 누수 없음). 단일 면접(한 번에
한 세션) 전제. 신호는 **완료 순**으로 반환되어 시간순이 아닐 수 있다 — 소비자는 각 신호의
타임스탬프(`t` / `window_start_s`)로 정렬한다(신호는 자기기술적).

엔드포인트(세션=한 면접 답변 턴):
  POST /sessions/{sid}/start          턴 시작(파이프라인 생성/리셋)
  POST /sessions/{sid}/media {frames,audio,now}  미디어 push + 그때까지 완료된 신호 반환
  POST /sessions/{sid}/end   {now}    end-of-turn, compact tail flush 신호 반환
  GET  /health

프레임/오디오는 base64(GilJob 와이어 포맷 그대로). 신호엔 channel 태그가 붙는다.
"""
from __future__ import annotations

import base64
import threading
from concurrent.futures import ThreadPoolExecutor

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


def create_app(*, evaluator=None, executor=None, **pipe_kwargs) -> FastAPI:
    """앱 팩토리. evaluator 미지정 시 실제 WindowEvaluator(vLLM)를 lazy 생성하고
    기동 시 best-effort 선warm한다. 실행기는 앱 레벨 공유(세션마다 생성하지 않음).
    테스트는 fake evaluator + executor=InlineExecutor()를 주입해 GPU 없이·동기적으로
    HTTP 배관을 검증한다(executor=None이면 백그라운드 스레드 3-레인 실행).
    """
    app = FastAPI(title="gje analysis sidecar")

    # 앱 레벨 공유 실행기 — 비언어 / 풀 평가 / compact tail 3-레인. 주입 시(테스트) 공용.
    if executor is not None:
        nv_exec = eval_exec = tail_exec = executor
        owns_exec = False
    else:
        nv_exec = ThreadPoolExecutor(max_workers=2, thread_name_prefix="gje-nv")
        eval_exec = ThreadPoolExecutor(max_workers=2, thread_name_prefix="gje-eval")
        tail_exec = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gje-tail")
        owns_exec = True

    state: dict = {"evaluator": evaluator, "sessions": {}}

    def get_evaluator():
        if state["evaluator"] is None:
            ev = WindowEvaluator()
            state["evaluator"] = ev
            warm = getattr(ev, "warmup", None)
            if warm is not None:  # 첫 턴 밖에서 CUDA 그래프 선warm(비차단)
                threading.Thread(target=warm, daemon=True).start()
        return state["evaluator"]

    def new_session(sid: str) -> dict:
        pipe = SlidingWindowPipeline(
            get_evaluator(),
            nv_executor=nv_exec, eval_executor=eval_exec, tail_executor=tail_exec,
            **pipe_kwargs,
        )
        sess = {"pipe": pipe}
        state["sessions"][sid] = sess
        return sess

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "sessions": len(state["sessions"])}

    @app.post("/sessions/{sid}/start")
    def start(sid: str) -> dict:
        old = state["sessions"].pop(sid, None)
        if old is not None:  # 재시작 시 이전 파이프라인 신호 수용 중단
            old["pipe"].close()
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
        pipe.poll(body.now)  # 즉시 반환(추론은 백그라운드) → 그때까지 완료된 신호만 드레인
        return {"session": sid, "signals": [_sig_dict(s) for s in pipe.drain()]}

    @app.post("/sessions/{sid}/end")
    def end(sid: str, body: EndIn) -> dict:
        sess = state["sessions"].get(sid)
        if sess is None:
            raise HTTPException(status_code=404, detail=f"unknown session {sid!r}")
        pipe: SlidingWindowPipeline = sess["pipe"]
        pipe.end_turn(body.now)  # compact tail flush — ≤eot_deadline_s 블록
        signals = [_sig_dict(s) for s in pipe.drain()]
        pipe.close()  # 신호 수용 중단(공유 실행기는 안 끔). 이후 도는 풀 평가 emit은 no-op
        del state["sessions"][sid]
        return {"session": sid, "signals": signals, "ended": True}

    @app.on_event("shutdown")
    def _shutdown() -> None:
        for sess in state["sessions"].values():
            sess["pipe"].close()
        state["sessions"].clear()
        if owns_exec:  # 앱 소유 실행기만 종료
            nv_exec.shutdown(wait=False)
            eval_exec.shutdown(wait=False)
            tail_exec.shutdown(wait=False)

    return app


# uvicorn 진입점: `uvicorn local_infer.service:app`
app = create_app()
