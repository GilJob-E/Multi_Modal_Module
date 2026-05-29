# 재정의: 실시간 턴 단위 native 멀티모달 면접 평가 모듈

> **(2026-05-24 디렉토리 정리)** 아래 본문의 옛 경로는 *이력 기록*이다. 실제 위치:
> 스파이크 스크립트 `tools/spike_*.py` → **`legacy/spikes/`**, 과거 증거 `.sisyphus/evidence/spike-*.json`·`phase3-prefill-effect.json` → **`legacy/evidence/`**(인덱스 `legacy/README.md`).
> `tools/turn_pipeline_demo.py`(Phase 3 하니스)는 **삭제됨**(폐기된 periodic-prefill 데모). 서빙 설정 `sglang/launch-configs/` → **`serving/`**(폴더명 sglang은 vLLM 채택 후 stale였음). 현역 코드는 `src/local_infer/`, 현재 증거는 `.sisyphus/evidence/{m2-window-eval,m5-e2e}.json`.

## Context (왜 이 작업을 하는가)

`local-infer`는 원래 "실시간 화상 입력 → 텍스트 응답을 최소지연 스트리밍하는 로컬 추론 모듈"로 시작했지만, 진행 중 **native audio "no-go" 검증과 그에 딸린 방어적 disclaimer 문서·3중 경로(native override / degraded fallback)** 로 흐름이 지저분해졌다. 사용자는 결과물이 마음에 안 들어 "핵심만 남기고 재시작"하기로 했다.

재정의된 목적은 명확하다: **로컬 LLM으로 nativeness와 latency를 동시에 최대화**해서, 면접 답변을 **언어(verbal)·청각(vocal)·시각(visual) 종합**으로 평가하는 풍부한 피드백을 **턴(답변) 단위로 즉시** 생성한다. 핵심 방법론은 **periodic prefill**(발화 중 선행 prefill → 턴 종료 시 즉시 generate).

리서치가 이전의 핵심 오해를 교정했다:
- **native 청각은 천장이 아니라 구현 버그였다.** Gemma 4 **E2B/E4B는 video+audio를 native 입력**받는다(ASR/번역 공식 지원). 이전 HTTP 400 "Invalid or unsupported audio file"는 ① payload를 `input_audio`로 보낸 포맷 오류(vLLM 규격은 `audio_url`) ② `vllm[audio]` extras 누락 ③ 30초 초과 가능성 때문일 공산이 크다.
- **31B·26B-A4B는 오디오 입력이 없다**(text/image/video만). 즉 오디오를 들으려면 E2B/E4B를 써야 한다 → 모델 트레이드오프 발생.
- E4B 오디오 공식 능력은 ASR/번역까지이고, prosody(음량/피치) 묘사는 **미보장 → 실측 필요**.

출처: [Gemma 4 blog](https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/), [Gemma audio docs](https://ai.google.dev/gemma/docs/capabilities/audio), [vLLM Gemma4 recipe](https://docs.vllm.ai/projects/recipes/en/stable/Google/Gemma4.html).

안전장치: 재시작 전 현재 전체 상태를 git 베이스라인으로 커밋 완료(commit `f80e447`, 203파일). 무엇을 지워도 복구 가능.

## 성공 기준 (재확인)

1. 출력 품질: 사용자가 제시한 예시 수준의 풍부한 verbal/vocal/visual 종합 평가.
2. 실시간성: 턴 종료(VAD/end-of-turn) 시 첫 토큰 지연 최소(목표 warm TTFT < 0.5s), periodic prefill로 달성.
3. nativeness: 청각·시각을 가능한 한 모델이 직접 이해(저수준 feature dump 지양).
4. 깔끔한 단일 인터페이스(vLLM 비노출), 모델/엔진 교체 시 인터페이스 불변.

---

## Phase 1 — 검증 스파이크 ✅ 완료 (2026-05-24)

**결과: 아키텍처 (1) 단일 E4B native AV 확정.** audio_url 규격 + vllm[audio] 파생 이미지로 E4B가 native AV를 HTTP 200 처리, prosody 묘사·평가 깊이·prefix 캐시 재사용 모두 실측 통과(2-스테이지 분기 폐기). 상세 `docs/DECISIONS.md` D5, 증거 `.sisyphus/evidence/spike-e4b-native-av.json`. 아래는 수행 기록.

목적: 문서로 못 정하는 경험적 미지수를 싸게 걷어내고 아키텍처 (1)단일 E4B vs (2)2-스테이지를 확정.

### 1.1 E4B 오디오 서빙 기동
- 새 launch config `sglang/launch-configs/vllm_e4b_audio.sh` 작성(31B용 `vllm_baseline.sh`는 보존).
- 핵심: `vllm[audio]` extras 포함 이미지/설치, E4B는 작아서 단일 GPU(TP 불필요).
  ```bash
  vllm serve google/gemma-4-E4B-it \
    --max-model-len 8192 \
    --limit-mm-per-prompt image=4,audio=1 \
    --enable-prefix-caching
  ```
- `/v1/models` ready 확인. 종료 시 GPU 언로드 규칙 준수.

### 1.2 payload 교정
- `native_payloads.py`의 `{"type":"input_audio",...}` → **`{"type":"audio_url","audio_url":{"url": "<data: 또는 file:// URL>"}}`** 로 교정.
- 오디오는 **16kHz mono WAV, ≤30초**. `native_audio.py`가 이미 mono 16kHz 추출 → 30초 클리핑만 추가.

### 1.3 프로브 (기존 `tools/probe_gemma4_real_video.py` 적응, 새 `tools/spike_e4b_native_av.py`)
`vid_0033.mp4`에서 **≤30초 윈도우**를 잘라 측정:
1. **Native AV 동작 + 전송 방식**: (a) `video_url` 단독으로 E4B가 영상의 오디오까지 듣는가, (b) `video_url` + 별도 `audio_url` 조합 — 둘 중 무엇이 HTTP 200 + 보고/들은 내용 일치하는지 확인.
2. **품질 루브릭**: 전체 verbal/vocal/visual 평가 프롬프트 → 출력이 예시 수준인가 채점(구조적 verbal 평가 / vocal 전달력 / visual 단서 각 항목 유무·깊이).
3. **prosody 프로브**: "음량 변화·말 속도·pause·억양 단조로움을 짚어줘" 류 프롬프트 → 실제 묘사하는가, 단순 전사만 하는가.
4. **지연**: E4B native AV generate의 TTFT/total 측정.
- 증거를 `.sisyphus/evidence/spike-e4b-native-av.json`에 기록.

### 1.4 결정 규칙 (GO/NO-GO → 아키텍처)
- E4B native AV 동작 **AND** 품질·prosody 충분 → **(1) 단일 E4B**.
- E4B native AV 동작하나 추론 얕음 **OR** prosody 약함 → **(2) 2-스테이지**: E4B가 native 청각(전사+가능한 vocal)·시각 추출 → **26B-A4B**(4B 활성, 빠름) 또는 **31B**가 종합 추론.
- VRAM: E4B(~8GB) 단독 스파이크 먼저. (2) 선택 시 E4B + 대형모델 2×4090(48GB) 동시 적재 가능성/순차 적재를 별도 검증.

---

## Phase 2 — 폐지 (Phase 3로 흡수, 2026-05-24)

원래 "군더더기 절단 & 깨끗한 토대"(배치 복구 + cruft 제거)였으나 두 전제가
무너져 별도 단계를 두지 않는다:
1. **재정의 wipe가 이미 cruft를 비웠다.** `audio_analysis.py`·fallback
   엔드포인트(`/audio`, `/generate-av-fallback`)·disclaimer 레이어·"not native
   success" 방어 문서는 작업트리에 없다 — "복구하지 않으면" 그만이라 제거 작업이
   없다. (히스토리는 `f80e447`에 보존.)
2. **검증된 경로가 복구 목록과 어긋난다.** 동작이 입증된 유일한 코드
   `tools/spike_e4b_native_av.py`는 `NativeAudioExtractor` 하나만 import하고
   payload는 인라인 dict로 만들며, 전송은 **샘플 `image_url` 프레임 + `audio_url`**다.
   `video_url`은 쓰지 않는다. 따라서 `native_media_store.py`(MP4→`video_url` 전용)와
   `native_payloads.py`(`video_url+audio` 하드코딩) 원형 복구는 **검증 안 된 video_url
   전송을 미리 되살리는** speculative 작업 → 하지 않는다.

남은 실질 작업은 ① living docs stale 교정(완료) ② Phase 3 JIT 복구 규칙
명문화(아래)뿐. `native_audio.py`(audio_url 교정 + 30초 캡)는 Phase 1에서 이미 복구됨.

## Phase 3 — 턴 단위 native 파이프라인 + periodic prefill ⚠️ 부분 완료 / latency 미검증 (2026-05-24)

**정정(2026-05-24):** 최초 "✅ periodic prefill 31.5배 단축(1.226s→0.039s)"은 **과대광고였다.** 하니스가 warm 시점에 **이미 최종 오디오를 손에 쥐고** 동일 prompt를 두 번 보낸 것이라, 측정한 건 **identical-prefix 캐시 재사용(best case)**뿐 — Phase 1이 이미 보여준 사실이다. 라이브에선 최종 오디오가 턴 종료 시점에야 확정되므로 그 prefix를 미리 데울 수 없다.

**실제로 입증된 것**: 파이프라인 동작 + 평가 품질(verbal/vocal/visual + prosody) + native 오디오 이해 + vLLM 숨긴 인터페이스. **미입증(핵심 갭)**: 간판 방법론 periodic prefill의 latency 실효 — 비싼 오디오 prefill은 턴마다 cold라고 가정해야 한다. 상세·다음 작업은 **## 남은 갭 + cold kill-test** 참조. 증거 `.sisyphus/evidence/phase3-prefill-effect.json`(best-case 수치이므로 그대로 신뢰 금지). 아래는 수행 기록.

- **평가자 인터페이스** (`src/local_infer/native_eval.py`): `NativeInterviewEvaluator` — `add_frame`/`set_audio_window`(턴 중 push) → `warm`(prefix 캐시 프라임) → `evaluate`(SSE 스트리밍). vLLM은 평가자 뒤에 숨김(성공 기준 #4).
- **periodic prefill 기제** (구현됨, 단 best-case에서만 검증): 평가 루브릭을 **system 프롬프트에 고정**, user 턴 = `[image_url 프레임…, audio_url, 고정 text]`. warm(max_tokens=1)과 evaluate가 전체 prefix를 공유하면 `--enable-prefix-caching` 풀히트. **단 이 풀히트는 warm/evaluate가 동일 오디오 객체를 쓸 때만 성립** — 라이브에선 최종 오디오를 미리 못 쥐므로 이 조건이 깨진다(= 갭의 핵심).
- **검증된 레시피 기준선**: 전송 = 샘플 `image_url` 프레임 + `audio_url` + 고정 text(스파이크 그대로). payload는 **인라인으로** 빌드(`native_payloads.py` 원형 복구 안 함 — video_url 모양이라 부적합).
- **JIT 복구 완료** (f80e447 → `src/local_infer/`, verbatim, cruft import 없음 확인): `vllm_client.py`, `vllm_stream.py`, `frame_store.py`. `pyproject.toml`은 `requests`만(HTTP 미구현이라 fastapi/uvicorn 제외).
- **30초 오디오 캡 ↔ 긴 답변**: rolling window(최근 윈도우 + 누적 요약)는 **미구현 — 범위 밖**(코어는 최신 ≤30초 윈도우만 평가). 추후 refinement.
- **video_url 재고 조건**: `native_media_store.py`·`native_payloads.py`는 video_url 전송을 별도 실측한 뒤에만 복구 검토(현재 미사용).
- 아키텍처: (1) 단일 E4B native AV 확정(Phase 1) — 2-스테이지 분기 폐기.

## Phase 4 — 백지화 (2026-05-24)

사용자 결정으로 폐지. 근거: ① 품질 루브릭 재적용·② periodic prefill 효과 측정은
Phase 3 하니스(`tools/turn_pipeline_demo.py`)가 이미 1회 실측으로 커버했고(단 ②는
best-case라 무효), ③ 정식 pytest 스위트는 현 단계에서 만들지 않는다. 진짜 다음
작업은 아래 cold kill-test.

## 남은 갭 + cold kill-test (현 단계 핵심)

### ✅ 결론 (2026-05-24 실측 — thesis 정정): periodic prefill은 ≤30s·E4B에서 **불필요**

cold kill-test와 신선 콘텐츠(`vid_0001`) 확증 스파이크 결과, 간판 방법론
periodic prefill이 풀려던 문제("비싼 오디오 prefill을 숨겨야 한다")가 **이 조건에선
존재하지 않는다.** 실측(`.sisyphus/evidence/spike-cold-prefill.json`):

- **cold 바닥이 이미 싸다.** 매번 unique=cache-miss인 오디오로도 end-of-turn TTFT가
  10s 0.08s / 20s 0.11s / 30s 0.12s(길이 비례 = 진짜 cold). Gemma 오디오 인코더가
  30s를 소수 토큰으로 압축하기 때문. 목표 <0.5s를 **periodic prefill 없이 충족.**
- **warm 전제 없음(Phase 3 정정의 핵심).** 신선 `vid_0001`로 서로 다른 30s 클립 6개를
  연속 발사 → 턴1(부팅) e2e 1.19s, **턴2~6(전부 unique cold) e2e 0.17~0.20s.** 클라이언트측
  추출(ffmpeg+base64) ~70ms 포함한 end-to-end도 <0.2s. per-turn 캐시 히트에 의존하지 않음.
- **유일한 비싼 턴 = 부팅 첫 호출 1.19s**(CUDA 그래프 1회성 컴파일). 기동 시 더미 요청
  하나로 선warm하면 첫 유저 턴부터 ~0.18s. per-turn에 warm을 끼워넣는 게 아님.
- **레버 A(인코더 청크 prefix-stable) = 미스**(워밍한 chunk1 KV 재사용 안 됨). 그러나
  절대 비용이 0.1s대라 **무의미** — periodic prefill로 아껴봐야 이미 sub-0.5s.
- **레버 B**: tail 1/2/5s prefill 55~72ms ≪ VAD hangover 500ms(숨길 게 없지만 여유).
- **보너스(레버 C 품질)**: 분할 2파트 eval ≈ 통오디오 eval(동일 내용·prosody) →
  >30s를 청크로 쪼개도 평가 품질 유지. **단 이는 latency가 아니라 긴-답변 커버리지용.**

**남은 진짜 과제(latency 아님)**: ① 부팅 선warm 1줄(기동 더미 요청) ② 30s 캡 ↔ 긴 답변
rolling window(품질/커버리지) ③ 라이브 VAD·스트리밍 캡처 파이프라인 엔지니어링.
thesis 재프레이밍은 사용자와 확정(README/DECISIONS 갱신 대상).

---

<details><summary>아래는 스파이크 이전의 설계·프레이밍(이력 보존)</summary>

**프레이밍(1차 원리, problem-solver 2026-05-24):** "오디오는 프리필 불가"는 **법칙이 아니라 검증 안 된 가정 3개의 합**이었다. 프리필 지연 이득 = "최종 오디오 KV를 턴 종료 *전에* 계산해 VAD 시점에 캐시돼 있게" 하는 것. 핵심 통찰: **프레임과 오디오는 대칭이다** — 시각 t에서 `[턴시작, t]` 오디오는 이미 도착·불변이고 모르는 건 미래뿐(프레임과 동일). "오디오 cold"가 성립하려면 ①Gemma 오디오 인코더가 클립 전체 global attention(앞 청크 토큰이 뒤에 의존) ②단일 블롭 전송 ③VAD trailing-silence lead time 무시 — 셋이 *동시에* 참이어야 하는데 ①은 미검증 가정, ②는 우리 선택, ③은 놓친 자원이다. Phase 3의 31.5배는 cold 현실을 회피(최종 오디오를 미리 쥠)한 best-case였다.

**오디오 VAD 지연 레버 (MECE):**
- **A. 청크 점진 캐싱** — 발화 중 오디오 청크를 데워 VAD엔 마지막 청크만 cold. 조건: 인코더 **청크 prefix-stable**(가정①의 반대). 효과 큼 = thesis 핵심.
- **B. VAD silence lead time** — VAD는 ~500ms 침묵 확인 후 발화하므로 *의미 있는 오디오는 침묵 시작 시 이미 확정* → 침묵窗에 prefill 선행. 조건 없음(무조건 가능), prefill<침묵窗이면 완전 은닉.
- **C. 오디오 윈도우 단축** — 마지막 N초만 평가(품질 트레이드오프). prefill ∝ 토큰 수.
- (D. 스트리밍 인코더는 모델 교체급이라 범위 밖.)
- **A·B는 곱셈**: A로 발화 중 대부분 캐시 → 침묵 시작 시 짧은 tail만 → B의 침묵窗에 흡수 → VAD에 완전 warm. 성립 시 <0.5s 현실적.

**진짜 미지수(thesis 생사):** Gemma 오디오 인코더가 **청크 prefix-stable한가**(레버 A 성립 여부). 이 하나가 전부를 가른다.

**스파이크 (`tools/spike_cold_prefill.py`, Phase 1식 kill-test):** 콘텐츠를 매번 다르게 줘 cold 강제.
1. **Cold 바닥 / 레버 C**: 오디오 길이별(5/10/20/30초) end-of-turn TTFT 격리 측정 — 진짜 baseline + "윈도우 얼마면 단독으로 0.5s 드나".
2. **레버 A (핵심)**: launch `--limit-mm-per-prompt audio>=2` 재기동. `[system, 청크1]` 데운 뒤 `[system, 청크1, 청크2]` → 청크1 KV 히트하나(자라는 오디오 캐시) + 청크 분할 eval이 통오디오만큼 일관한가. → 인코더 prefix-stability 직접 판정.
3. **레버 B 정량**: 실제 VAD hangover(예 500ms) vs "tail만 cold일 때 prefill 시간" — tail이 침묵窗에 들어가나. (참고: 프레임-warm 한계도 부수 측정 — 예상 marginal.)

**결정 규칙:**
- 레버 A **히트 AND 청크 eval 일관** → periodic prefill viable. Phase 3를 청크-오디오 스트리밍 워밍으로 재설계, end-of-turn=마지막 청크 prefill(+레버 B)로 <0.5s 도달 재측정.
- 레버 A **미스** → 오디오 통째 cold 확정. 그래도 죽지 않음 — **레버 B+C 조합**으로 갈 수 있나 측정(짧은 윈도우를 침묵窗에 prefill). 그것도 안 되면 <0.5s 목표 수정을 사용자와 결정.

증거 `.sisyphus/evidence/spike-cold-prefill.json`. GPU 위생 준수(`docker stop` + nvidia-smi).

</details>

## 처리 전략 통합 + 시각 시간축 트랙 (다음 단계, 2026-05-24)

cold kill-test(D6)와 시각 스파이크(D7)로 thesis가 **periodic prefill → 모달리티별 처리
전략**으로 재정의됨. 이를 턴 파이프라인으로 통합한다.

**목표 아키텍처:**
- **청각/언어 트랙**: ≤30s 오디오 윈도우를 모델에 통째로(cold로 충족). 기동 시 더미 요청
  1회로 CUDA 그래프 선warm. 긴 답변은 rolling window(최신 윈도우 + 누적 요약) — 미구현.
- **시각 트랙 (holistic 기본, 2026-05-24 problem-solver 재프레이밍)**: 프레임 몇 장 +
  오디오를 한 프롬프트에 줘 모델이 시선·태도·제스처를 통째로 *질적* 평가(north-star).
  deliverable이 풍부한 질적 피드백이므로 이게 기본. *(프레임별 분석+집계는 정밀 시간추적이
  하드 요구일 때만의 narrow fallback — 강등됨. D7 참조.)*
- **융합**: end-of-turn에 audio 평가 + visual 타임라인 집계를 결합해 단일 verbal/vocal/
  visual 피드백.

**열린 천장(범위·의사결정 필요):**
- 시각 카운팅 fidelity(인접값) — 질적 평가엔 허용, 정확 카운트 과제엔 모델 교체급.
- 30s 오디오 캡 ↔ 긴 답변 rolling window(품질/커버리지).
- 라이브 캡처(웹캠/마이크 → VAD/end-of-turn → 프레임 cadence) 파이프라인 엔지니어링.

**다음 작업(확정, 2026-05-24)**: 실제 면접 클립(vid_0001/vid_0033/video.mp4)에 **holistic
native AV 평가**(프레임 3~5장 + 오디오 한 프롬프트 = 기존 `native_eval` 방식)를 돌려, 출력의
**시선/고개/태도 + verbal/vocal 피드백을 루브릭으로 채점** — 손가락-카운트류 메트릭이 아니라
deliverable 자체를 검증. product-관련 신호가 입증적으로 빠질 때만 그 신호 한정 프레임별 보강 고려.

## 프로덕트 — GilJob 사이드카 분석 모듈 (현 단계, 2026-05-24 확정)

실험/스파이크 단계 종료. 핵심 미지수(native AV 품질·prosody·video_url 시간축 binding·
latency·슬라이딩 윈도우 viability)는 모두 입증됨. 이제 **버리는 스파이크가 아니라
유지보수 가능한 프로덕트 모듈**을 짠다.

### 궁극 목적 (2026-05-24 사용자 정의) — 사람 같은 실시간 비언어 상호작용
면접관 아바타가 지원자가 말하는 동안 **끄덕이거나 갸우뚱**하고, 지원자 비언어를 읽어
속으로/겉으로 평가하거나, 역으로 비언어 신호를 준다(backchannel). Gemini Live는 오디오
응답이 일이라 이걸 못 한다 = gje의 델타. **GilJob엔 아바타 렌더링이 이미 있으나
(단순 SVG는 면접 *상태*로 눈·입만, 3D `SpatialAvatar`는 Gemini 오디오 립싱크만) 지원자가
말하는 동안 무반응** — gje가 *무엇을·언제* 표현할지 구동하는 **두뇌** = 이 프로젝트의
마지막 퍼즐.

### 타깃과 분담
- **타깃 = GilJob**(`github.com/GilJob-E/GilJob`, 라이브 `giljob-e.giljobe2.workers.dev`):
  Cloudflare Workers + React/Vite, **Gemini Live API**(`gemini-3.1-flash-live-preview`)
  한국어 면접. **최소 변경**이 제약.
- **GilJob 소유(불변)**: 캡처, 수동 VAD(`activityStart/End` 버튼), 라이브 대화, **집계(Gemini)**,
  아바타 렌더링(`Avatar.tsx` / `SpatialAvatar.tsx` `@spatialwalk/avatarkit`).
- **gje 소유**: 윈도우잉 + native AV 분석. **두 출력 채널** —
  ① **실시간 비언어 반응**(핵심·신규): 발화 중 지원자 비언어 read → 아바타 반응 큐
     (끄덕임/갸우뚱/표정), 저지연 연속(~1–3s cadence), 아마 Gemini 안 거치고 아바타 직결.
  ② **평가 신호**: 16초 윈도우/end-of-turn native AV 분석 → 구조화 신호를 Gemini에 주입(다음질문 반영).
  캡처/VAD 안 함. 두 채널 모두 native 이해로(저수준 feature 금지).

### 데이터 흐름 (탭 → 분석 → 주입)
1. **탭**: `worker/ws-bridge.ts:80–97`에서 미디어 프레임을 gje로 fire-and-forget 포워딩
   (Gemini로는 그대로 전송). 입력 = 오디오 16kHz PCM Int16 base64(~128ms), 비디오
   640×480 JPEG base64 **@1fps**, activity 마커.
2. **윈도우 분석**: gje가 턴 동안 **16초 윈도우**를 누적 → 각 윈도우를 **독립 추론**
   (발화 중 분산처리, KV prefix-stability 불필요). 윈도우 = 1fps 프레임 16장을 **mp4로
   재인코딩 → `video_url`**(시간축 binding, D8) + 16초 PCM→wav **`audio_url`** 조합.
   multi-image 덤프 금지(binding 깨짐, D7). 16프레임 < 32 상한 OK.
3. **end-of-turn**: `activityEnd` 시 마지막(부분) 윈도우만 cold(~1s) 처리 → 그 윈도우 신호 emit.
   **gje는 윈도우 신호를 병합/종합하지 않는다** — per-window 신호를 그대로 내보내고 **집계는 Gemini 몫**.
4. **주입**: `src/lib/system-instruction.ts` 시스템프롬프트 컨텍스트로 다음 턴에 삽입.
   ⚠️ **1007 불변식**: `realtimeInput.text`를 activity 마커와 섞으면 WS 1007 종료 →
   주입은 activity 윈도우 밖/시스템프롬프트 경로로만.

### 레이턴시 예산 (라이브라 빡빡)
- 윈도우 분석은 발화 중 흡수. end-of-turn 잔여 = 마지막 윈도우(~0.72s combo) + 병합.
- 부팅 1회 CUDA 그래프 비용(~1.2s)은 기동 더미 요청으로 선warm.
- 목표: `activityEnd` → 신호 주입까지 thinking 갭(~1–2s) 안에 완료.

### 출력 계약 (gje의 산출물 = 분석 신호. 렌더링/주입은 소비자 측)
gje는 **구조화된 분석 신호만** 낸다. 소비(아바타 렌더링·Gemini 주입)는 GilJob 측 일 — 이 레포 밖.
- **① 실시간 비언어 신호**: `{signal: engaged|nodding-worthy|hesitation|..., intensity, t}`
  류 저지연 연속(~1–3s cadence). *지원자 비언어의 read* — 이걸 어떤 아바타 제스처로 매핑할지는 소비자 결정.
- **② 평가 신호**: 구조화 JSON, 예 `{verbal:{...}, vocal:{prosody, pace, pauses,
  intonation}, visual:{eye_contact, posture, expression, gesture_over_time}, key_observations:[]}`.
gje는 최종 산문 피드백도, 아바타 제어 명령도 만들지 않는다.

### 인터페이스 경계
gje = **사이드카 HTTP 서비스**(Worker가 호출). vLLM은 서비스 뒤에 숨김(성공기준 #4).
`GEMINI_API_KEY`는 gje가 절대 안 봄(Worker가 프록시). same-origin 게이트 유지.

### 범위 경계 (스코프 크립 방지)
**이 레포 = 사이드카 분석 모듈의 완성, 그 이상도 이하도 아니다.** 다음은 **gje 범위 밖**(소비자/GilJob 측):
아바타 제어 API(`@spatialwalk/avatarkit`)·렌더링·제스처 매핑, WS 브리지 탭 구현, 시스템프롬프트
주입·1007 처리. 이것들은 gje가 *플러그되는 환경*으로만 알면 되고, gje가 만들지 않는다.
사람같은 상호작용은 *왜 이 신호가 필요한가*(목적)일 뿐, gje의 산출물 경계는 **분석 신호에서 끝난다.**

### 열린 항목 (gje 범위 내)
- **분석 출력 계약 정의 + 검증** — 실제 면접 클립에서 E4B가 *신뢰성 있게* 읽어내는 비언어·평가
  신호가 무엇인지 실측해 ①②의 스키마를 확정(evidence-first). **빌드 첫 작업.**
- **2-tier 처리**: 반응 신호 cadence(~1–3s 짧은 window read) vs 평가 cadence(16초/턴)를 한 모듈에서.
  fast tier도 native 이해로(저수준 feature 금지).
- 16초 윈도우 경계서 잘린 제스처/문장 처리. (윈도우 신호 *병합*은 gje 일 아님 — Gemini가 집계.)
  per-window 신호 패키징/스트리밍 형식만 정의.
- 긴 답변 rolling window. 라이브 1fps ↔ 분석 품질(시간해상도 1fps 고정).
- gje 서비스 인터페이스(HTTP) + 배포 형태(GilJob edge와 별개 로컬/사설 호스트).

### 구현 산출물(예정)
- `src/local_infer/native_eval.py` 확장: 윈도우 스케줄러 + 독립 추론 + per-window 신호 emit(집계 없음).
- 사이드카 HTTP 서비스(`app.py` 신규, fastapi/uvicorn 의존 추가) — 탭 수신 + 신호 반환.
- 윈도우 재인코딩 유틸(1fps JPEG들 → mp4, PCM → wav).
- GilJob 측 최소 패치(별도 repo): ws-bridge 탭 5줄 + system-instruction 주입.

## Project-manager 스캐폴딩 (병행)

- 프로젝트 프레임 문서(목적·기준·디렉터리)와 CLAUDE.md를 교정된 내용으로 갱신.
- 메모리 저장: "E4B native audio는 viable; 이전 no-go는 `input_audio` payload 버그·`vllm[audio]` 누락·30초 캡 때문" — project 메모리로 기록(재발 방지).

## 핵심 변경 파일 요약

| 파일 | 작업 |
|---|---|
| `serving/vllm_e4b_audio.sh` | 신규 — E4B+audio 서빙 |
| `tools/spike_e4b_native_av.py` | 신규 — Phase1 스파이크(기존 probe 적응) |
| `src/local_infer/native_payloads.py` | 교정 — `input_audio`→`audio_url` |
| `src/local_infer/native_audio.py` | 30초 클리핑 추가 |
| `src/local_infer/app.py` | fallback 엔드포인트 제거 + 턴/prefill 엔드포인트 |
| `src/local_infer/audio_analysis.py` 등 | 제거 |
| README / INFERENCE_PIPELINE / docs / CLAUDE.md | 재작성 |

## 미해결·실측 의존 항목
- E4B 단일 추론이 목표 평가 깊이에 도달하는가 (Phase1이 판정).
- E4B가 prosody를 묘사하는가, 아니면 전사만 하는가 (Phase1).
- vLLM 멀티모달 prefix 캐시가 요청 간 재사용되어 periodic prefill이 실효가 있는가 (Phase3/4 측정).
- 아키텍처 (2) 선택 시 E4B + 대형모델 2×4090 동시 적재 가능 여부.
