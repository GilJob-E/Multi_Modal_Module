# 야간 루프 리포트 — 슬라이딩 윈도우 분석 모듈 (2026-05-24)

브랜치 `feat/sliding-window-pipeline` (master에서 분기, **미푸시·미머지**).

## 결과: M0–M5 전부 완료·테스트 통과·커밋

| M | 내용 | 테스트 | 커밋 |
|---|---|---|---|
| — | D8 + 제품피벗 문서(이전 세션 작업 보존) | — | 7d1b6c2 |
| M0+M1 | signals.py(두 채널 스키마) + window_assembly(1fps JPEG→mp4, PCM→wav, 캡) | 단위 5건 PASS(GPU 불필요) | b7d6698 |
| M2 | WindowEvaluator(video_url+audio_url→E4B→JSON 두 채널) + vllm chat + clip_stream | 통합 PASS(실클립) | 181b5cf |
| M3 | SlidingWindowPipeline(윈도우 독립추론, 집계없음, end-turn tail) | 스케줄링 단위 PASS(fake) | a313f57 |
| M4 | FastAPI 사이드카 service.py(start/media/end) | 배관 PASS(TestClient+fake) | 066ee18 |
| M5 | e2e 2클립 시뮬 라이브 + 지연측정, GPU stop | PASS | 7c46916 |

## 실측 (클립별 — 과대일반화 금지)

- 비언어 read(채널①, 3s 윈도우): mean **0.47s** (0.4–0.51, 두 클립 일관) → backchannel cadence 충분.
- 평가 윈도우(채널②, 16s): 1.66–4.65s (생성 길이 따라).
- **end-of-turn 확정 지연: vid_0001 2.46s / vid_0033 2.13s** (다음질문 반영 임계경로).
- vid_0001(43.5s): 비언어 15·평가 3 / vid_0033(50.3s): 비언어 17·평가 4.

## 아침 검토 결정목록 (자율 진행 시 택한 기본값 + 열린 것)

1. **확정지연 ~2.5s** — 이상(~1-2s)보다 약간 큼. eval-tail 생성이 지배. 최적화 후보:
   eval 스트리밍/ max_tokens 축소 / 턴 끝 직전 완성 평가윈도우 있으면 eval-tail 스킵. **검토 요망.**
2. **의존 설치 = venv**(`.venv`, py3.12 system-site-packages). pip/root 없어 시스템 설치 불가 →
   uv venv 사용. 실행 시 `.venv/bin/python` 필요(fastapi import). 시스템 python3는 fastapi 없음. **방식 승인 요망.**
3. **채널① 비언어 read에 오디오 포함**(video-only 아님) — 머뭇거림/톤 위해. 0.47s로 충분. 되돌리기 쉬움.
4. **video.mp4 e2e 제외** — 오디오 트랙 없는 손가락 GT 클립이라 AV 평가 부적합. vid_0001/0033만 사용.
5. **스키마 라벨 신뢰성 미검증** — NONVERBAL_STATES(engaged/hesitant/…)와 eval JSON 키는 잠정.
   M5가 샘플은 냈으나 "E4B가 라벨을 신뢰성 있게 구분하는가"는 미검증. **스키마 확정 전 검증 필요.**
6. **cadence 기본값** 비언어 3s / 평가 16s. 16s=Gemma 2fps 풀밀도 근거(D8).

## 범위 밖(레포 경계 — 손대지 않음)

GilJob측 WS 브리지 탭(`worker/ws-bridge.ts`)·시스템프롬프트 주입·1007 처리·아바타 제어/렌더링,
신호 집계(Gemini 몫). 이 모듈은 분석 신호 emit + HTTP 서비스에서 끝.

## 실행법

```
서버:  HF_TOKEN=... bash sglang/launch-configs/vllm_e4b_audio.sh   # E4B + video:1
서비스: PYTHONPATH=src .venv/bin/python -m uvicorn local_infer.service:app --port 8001
테스트: PYTHONPATH=src .venv/bin/python tests/test_window_assembly.py   # GPU 불필요
        PYTHONPATH=src .venv/bin/python tests/test_turn_pipeline.py     # GPU 불필요
        PYTHONPATH=src .venv/bin/python tests/test_service.py           # GPU 불필요
        PYTHONPATH=src .venv/bin/python tests/test_window_eval.py       # 서버 필요
        PYTHONPATH=src .venv/bin/python tests/test_e2e_pipeline.py      # 서버 필요
```
