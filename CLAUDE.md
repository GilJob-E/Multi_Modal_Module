# Project Orchestration — gje

**gje**는 로컬 LLM(vLLM + Gemma 4)으로 면접 답변을 **언어·청각·시각
종합 평가**해 풍부한 피드백을 **턴 단위로 즉시** 생성하는 추론 모듈이다. 핵심은
"local LLM으로 nativeness와 latency를 동시에 최대화"이고, 핵심 방법론은
**periodic prefill**이다. 이 워크스페이스는 2026-05-24에 재정의 후 깨끗하게
재시작되었고(이전 구현 전체는 git 태그 `baseline-pre-rescope` = `f80e447`에 보존),
아래는 이 프로젝트를 여러 세션에 걸쳐 운영하기 위한 가이드다. 문서·소통은 한국어.

## 1. Establish the project frame

목적과 디렉터리는 이미 워크스페이스에 박혀 있다. **채팅이 아니라 이 문서들을 기준**으로 움직이고, 진화하면 함께 갱신한다(living documents):

- **Project overview & 성공 기준** — `README.md`
- **실행 계획 (Phase 1 검증 스파이크부터)** — `docs/PLAN.md`
- **리서치 결론 (Gemma 4 바리언트·native 오디오·출처)** — `docs/RESEARCH.md`
- **결정과 근거 (엔진/벤치/모델, 재사용 코드 포인터)** — `docs/DECISIONS.md`

**현재 상태 (2026-05-24, holistic 피벗):** Phase 1·2 완료. **cold kill-test 완료 → periodic prefill 폐기**: ≤30s·E4B에서 오디오 cold 바닥이 이미 싸다(30s TTFT ~0.12s, 신선 클립 6연발 턴2~6 e2e 0.17~0.20s, per-turn warm 전제 없음). 비싼 건 부팅 1회(1.19s)뿐 → 기동 더미 요청으로 선warm. 레버 A(오디오 청크 prefix-stable)=미스였으나 절대비용이 sub-0.5s라 무의미. **thesis는 "periodic prefill" → "모달리티별 처리 전략"으로 재정의됨**: 오디오는 통째로(latency는 모델 속성), **시각은 holistic native 평가**(프레임 몇 장+오디오 한 프롬프트로 시선·태도·제스처 질적 평가)가 기본 — 다중이미지 binding은 깨지지만 정밀 시간추적은 goal이 요구 안 함(프레임별+집계는 narrow fallback으로 강등). **다음 작업: 실제 클립에 holistic native AV 평가를 돌려 출력을 루브릭으로 채점**(deliverable 검증). 미측정 sliver = native `video_url` 전송 경로(검증된 건 `image_url`+`audio_url`뿐) — 재프레이밍상 speculative라 명분 선행 필요. 상세 `docs/PLAN.md` "## 남은 갭"·"## 처리 전략 통합". 재사용 코드는 import 시점에 `git show f80e447:local-infer/src/local_infer/<f>.py`로 `src/local_infer/`에 둔다.

**프로덕트 단계 전환 (2026-05-24):** 실험/스파이크 종료, 핵심 미지수 모두 입증. gje는 독립 앱이 아니라 **GilJob 면접앱**(`github.com/GilJob-E/GilJob`, Gemini Live API 기반)에 붙는 **사이드카 모듈**이다. **궁극 목적 = 사람 같은 실시간 비언어 상호작용**: 면접관 아바타가 지원자가 말하는 동안 끄덕이고 갸우뚱하고, 비언어를 읽어 반응한다(backchannel). Gemini Live는 못 하는 일 = gje의 델타. GilJob엔 아바타 렌더링이 이미 있으나 지원자에 무반응 — gje가 *무엇을·언제* 표현할지 구동하는 **두뇌 = 마지막 퍼즐**. gje가 내는 건 **분석 신호 두 종류뿐**: ① 실시간 비언어 read(~1–3s) ② 평가 신호(16초 윈도우/턴). **gje 범위 = 분석 모듈의 완성, 산출물은 신호에서 끝남** — 아바타 렌더링·제스처 매핑·WS 탭·시스템프롬프트 주입·1007은 전부 소비자(GilJob) 측, gje가 만들지 않는다(스코프 크립 금지, 사용자 강조). 사람같은 상호작용은 *왜*(목적)일 뿐. 캡처/VAD도 GilJob 소유. 빌드 스펙·범위경계 `docs/PLAN.md` "## 프로덕트 — GilJob 사이드카", 상세 [[giljob-integration-target]]. (이전에 multica로 오인했으나 무관한 별개 프로젝트.)

**반드시 기억할 사실 (재발 방지):**
- 오디오는 Gemma 4 **E2B/E4B에만** 있다. 31B·26B-A4B는 오디오 입력 불가.
- 이전의 audio "no-go"는 모델 천장이 아니라 **payload 버그**였다 — vLLM Gemma 4 오디오 콘텐츠 타입은 **`audio_url`**(`input_audio` 아님), `vllm[audio]` extras 필요, 오디오 16kHz mono ≤30초. 다시 "능력 한계"로 결론내지 말 것.
- **저수준 feature extraction으로 빠지지 말 것.** 목표는 모델이 직접 이해하는 native 평가다.
- `vid_0033.mp4`는 Phase 1 fixture, gitignore라 git에 없으니 **삭제 금지**(소실 시 복구 불가).
- **GPU 위생**: 모델 미사용 시 컨테이너 stop + `nvidia-smi`로 VRAM 해제 확인.

## 2. Context management

Context that lives only in one chat is lost the moment the session ends. Persist
it deliberately:

1. **Hierarchical folders with `CLAUDE.md`.** Organize the workspace into nested
   folders. Every folder gets a `CLAUDE.md` describing its contents; update it
   whenever the contents change.
2. **Memory layers (둘 다 사용).** 작업 중 핵심 행동·발견을 그때그때 기록한다 — 끝에 몰아서 하지 않는다. 두 레이어를 역할로 나눠 쓴다:
   - **파일 메모리** — `~/.claude/projects/-home-kio-workspace-gje/memory/`. 해너스가 세션 시작 시 자동 로드하는 **빠른 세션 간 컨텍스트**. 한 파일에 한 사실 + `MEMORY.md` 인덱스.
   - **mem0** — [mem0](https://mem0.ai) (mem0-mcp 서버 / CLI). 세션·에이전트를 넘어 살아남아야 할 **장기·교차 에이전트 메모리**.
3. **Git.** Track core issues and deliverables in version control so history and
   rationale are recoverable.
4. **Cross-reference.** Other agents and future sessions should actively read
   the memory layers (2) and git history (3) before acting, rather than
   reconstructing context from scratch.
5. **Reflections.** When the user asks for a retrospective on a specific issue,
   record it to mem0 separately with a recurrence-prevention measure (run the
   `kio-skills:reflector` skill) so the same mistake doesn't return.

## 3. Route work to the right skill

Match the project phase to the skill built for it. 스킬들은 `kio-skills` 플러그인으로 설치돼 있고, Skill 도구나 `/<name>` 슬래시 커맨드로 호출한다.

### Research
- `kio-skills:researcher` — gather information and data from the web and documents.
- `kio-skills:problem-solver` — reframe the gathered data with first-principles, logic-tree, and MECE thinking.

### Planning
- `kio-skills:griller` — interview the user until intent is fully aligned and refined.
- `kio-skills:grill-docs` — the same grilling, anchored to the project's documents and domain language.
- `kio-skills:round-table` — convene parallel agent personas for deeper, multi-perspective decisions.

### Implementation
- `kio-skills:karpathy-guidelines` — concise behavioral guardrails for writing code.

### Feedback
- `kio-skills:evaluator` — separate doer from checker; spawn agents to score and critique deliverables (iterative TDD-style loop).
- `kio-skills:reflector` — reflect on the session and record lessons with prevention measures.

