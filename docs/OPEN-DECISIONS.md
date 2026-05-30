# 미결 결정 (보류 — 사용자 검토 대기)

야간 루프(2026-05-24, 브랜치 `feat/sliding-window-pipeline`)가 슬라이딩 윈도우 모듈
M0–M5를 완성하며 자율 진행 중 택한 기본값과 열린 항목. **머지·확정 전 사용자 검토 대상.**
원 실측·맥락은 `.sisyphus/loop-report.md`, `.sisyphus/evidence/m5-e2e.json`.

| # | 항목 | 현재 상태(기본값) | 검토 포인트 |
|---|---|---|---|
| 1 | **end-of-turn 확정 지연** | ~~동기 풀-eval: 비평 후 8.01s~~ → **해결·실측 완료(D9, 2026-05-30): 백그라운드 3-레인 + compact tail. eot 0.87s/0.72s ≤2.5s ✓**(서버 실측, `m5-e2e.json`). | tail 2키 스키마(summary/critique)+잘린-JSON 복구로 교정(5키는 160토큰서 truncate→tail 0개였음). 채널① 0.65s(평가에 안 막힘). 발화중 블로킹도 백그라운드화로 해결. **닫힘.** |
| 2 | **의존성 설치 방식** | `.venv`(uv, py3.12 system-site-packages) | pip/root 없어 시스템 설치 불가. 실행 시 `.venv/bin/python` 필수. 배포 시 컨테이너/이미지 전략과 정합 필요. **방식 승인.** |
| 3 | **채널① 비언어 read에 오디오 포함** | 포함(video-only 아님) | 머뭇거림/톤 반영 위해. 0.47s로 충분. video-only로 더 줄일지 여부(되돌리기 쉬움). |
| 4 | **video.mp4 e2e 제외** | 제외 | 오디오 트랙 없는 손가락 GT 클립이라 AV 평가 부적합. vid_0001/0033만 사용. |
| 5 | **출력 스키마 라벨 신뢰성** | 잠정(NONVERBAL_STATES, eval JSON 키) | M5가 샘플은 냈으나 "E4B가 라벨(engaged/hesitant/…)을 신뢰성 있게 구분하는가"는 미검증. **스키마 확정 전 evidence-first 검증 필요.** |
| 6 | **cadence 기본값** | 비언어 3s / 평가 16s | 16s = Gemma 2fps 풀밀도 근거(D8). 비언어 3s는 임의 — 백채널 자연스러움과 비용으로 조정 가능. |

## 범위 경계 (재확인 — 이 레포 밖, 건드리지 않음)
GilJob측 WS 브리지 탭 · 시스템프롬프트 주입 · 1007 처리 · 아바타 제어/렌더링 · 신호 집계(Gemini 몫).
이 모듈은 **분석 신호 emit + HTTP 서비스**에서 끝난다. (스코프 크립 방지.)
