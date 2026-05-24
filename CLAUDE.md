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

**현재 상태:** Phase 1·2 완료(아키텍처 (1) 단일 E4B native AV 확정, Phase 2 폐지·흡수). **Phase 3**에서 평가자 인터페이스·품질·nativeness는 구현됐으나 **간판 방법론 periodic prefill의 latency 실효는 미입증**(최초 "31.5배"는 best-case 과대광고, 정정됨 — 라이브에선 최종 오디오를 미리 못 데움). **다음 단계는 cold kill-test 스파이크**(`docs/PLAN.md` "## 남은 갭"): 오디오 cold 바닥 + 청크 점진 캐싱 가능 여부로 thesis 생사 판정. Phase 4 백지화. 재사용 코드는 import 시점에 `git show f80e447:local-infer/src/local_infer/<f>.py`로 `src/local_infer/`에 둔다(경로 리맵).

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

