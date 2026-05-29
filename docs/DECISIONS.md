# 결정과 근거

작성 2026-05-24. 이전 구현의 결정 중 **유효한 것만** 추려 보존. 전체 이력은 git 베이스라인 `f80e447` 참조.

## D1. 추론 엔진 = vLLM (확정)

- SGLang은 No-Go: 동일 모델 fp8가 2×4090 24GB에서 메모리/성능 한계, AWQ 4bit는 Gemma vision tower compressed-tensors 미지원으로 기동 실패.
- vLLM은 `gemma-4-31B-it` fp8 TP=2를 안정 구동, warm TTFT 0.3s 이하 확인.
- (상세 SGLang 실험 로그는 베이스라인 `sglang/EXPERIMENT_LOG.md`에 보존.)

## D2. 입력 레이턴시 특성 (Phase 0 벤치, 보존 수치)

`gemma-4-31B-it`, fp8, TP=2, 2×4090, max_model_len 4096. 고정 system prompt prefix.

| 입력 방식 | cold TTFT | warm TTFT | 비고 |
|---|---|---|---|
| `image_url[]` N=1 | 2.77s | 0.19s | |
| `image_url[]` N=3 | 2.01s | 0.17s | 권장 영역 |
| `image_url[]` N=5 | 2.01s | 0.24s | 권장 영역 |
| `image_url[]` N=10 | 4.43s | 0.16s | cold prefill 비용 증가 |
| `video_url` 30초 전체 | ~7.98s | — | 실시간 부적합 |

**핵심**: 매 턴 전체를 새로 이해시키는 게 아니라 **세션별 prefix를 캐시에 태우는 구조**가 warm TTFT를 좌우 → periodic prefill의 근거. (벤치 원본 영상 `video-test/sample*.mp4`는 재시작 시 삭제했고, 수치만 여기 보존.)

## D3. 모델 선택 트레이드오프 (재정의로 부상)

- 오디오를 들으려면 **E2B/E4B**(오디오 native). 단 추론·시각 능력은 작은 모델.
- 최강 추론·시각은 **31B/26B-A4B**지만 **오디오 입력 불가**.
- → 둘을 동시에 못 가짐. 아키텍처 (1) 단일 E4B vs (2) 2-스테이지(E4B 청각 → 26B/31B 융합)는 Phase 1 스파이크 결과로 확정. 상세는 `RESEARCH.md`.

## D5. 아키텍처 = (1) 단일 E4B native AV (확정, Phase 1 스파이크 2026-05-24)

스파이크 실측으로 D3의 분기를 (1)로 확정. 근거(증거 `.sisyphus/evidence/spike-e4b-native-av.json`):
- `audio_url`(data URL) 규격 + `vllm[audio]` 파생 이미지로 E4B가 native AV를 HTTP 200 처리 — 이전 "no-go"는 모델 천장이 아니라 **`input_audio` payload + extras 누락** 버그였음 실측 확인.
- E4B가 prosody(음량·속도·pause·억양)를 **전사가 아니라 실제 묘사**, verbal/vocal 평가 깊이 충분 → 2-스테이지 융합 불필요.
- warm TTFT 0.03–0.38s. 동일 오디오 prefix가 요청 간 캐시 재사용됨(2번째 호출 0.03s). ⚠️ **정정(D6)**: 당시 이를 "periodic prefill 실효 입증"으로 적었으나 그건 identical-prefix 재사용일 뿐 — 라이브 cold 조건과 무관. 실제로는 D6에서 periodic prefill 자체가 불필요로 판명.
- 서빙: 파생 이미지 `vllm-gemma4-audio:local`(nightly + librosa/soundfile), E4B 단일 GPU ~22.7GB, `--limit-mm-per-prompt '{"image":4,"audio":1}' --enable-prefix-caching`.

## D6. periodic prefill 폐기 — 오디오 cold가 이미 싸다 (확정, cold kill-test 2026-05-24)

간판 방법론이던 periodic prefill은 ≤30s·E4B에서 **불필요**. 근거(증거 `.sisyphus/evidence/spike-cold-prefill.json`):
- 매번 unique=cache-miss인 오디오로도 end-of-turn TTFT가 길이 비례 10s 0.08s / 20s 0.11s / **30s 0.12s** — Gemma 오디오 인코더가 클립을 소수 토큰으로 압축하므로 cold prefill이 싸다.
- 신선 `vid_0001`로 서로 다른 30s 클립 6연발: 턴1(부팅) e2e 1.19s, **턴2~6(전부 cold) e2e 0.17~0.20s**(ffmpeg+base64 추출 ~70ms 포함). per-turn warm 전제 없음 — Phase 3 "31.5배"(최종 오디오 미리 쥔 best-case) 철회.
- 유일한 비싼 턴 = 부팅 첫 호출 1.19s(CUDA 그래프 1회 컴파일) → 기동 더미 요청으로 선warm.
- 레버 A(인코더 청크 prefix-stable)=미스지만 절대비용 0.1s대라 무의미. 레버 B(tail prefill 55~72ms ≪ VAD hangover 500ms)는 숨길 게 없을 만큼 여유.
- **결론**: 오디오 latency는 모델 속성으로 충족. 별도 prefill 기법 대신 ≤30s 윈도우를 통째로 보낸다.

## D7. 시각 시간축 = 프레임별 분석 + 집계 (확정, 시각 스파이크 2026-05-24)

다중 프레임을 한 프롬프트에 덤프하는 현재 `native_eval`식은 **미세 시간축 과제에 부적합**. 근거(증거 `spike-visual-fingers.json`, `spike-visual-temporal-v2.json`; GT 손가락 5 2 10 9 4 2 1 4 5 10):
- **단일 프레임 카운팅은 320x240에서도 정확**(4/4: 0,0,10"양손5개씩",2"V자").
- 그러나 10~16장을 한 프롬프트에 넣으면 `0,1,2,3,4,5` 식 **환각 + 출력 길이 불일치 — 다중이미지 시간 binding이 깨짐**. 거시적 시각 단서(태도·자세)엔 OK, 미세 시퀀스엔 불가.
- **프레임별 단일호출 + 타임라인 집계**는 실제 제스처를 추적(선명한 것 ~6/10 회복).
- latency: 프레임당 55~72ms, 73장 병렬 0.50s. **프레임은 턴 내내 도착 → 발화 중 분산처리, end-of-turn은 집계만(~0)** = incremental 처리의 진짜 자리(오디오와 대비, D6).
- 잔여 천장 = **인접값 카운팅 fidelity**(4 vs 5 엄지, 9 vs 10). 선명한 프레임에서도 나는 모델/해상도 한계 — 정확 카운트엔 블로커, 질적 body-language엔 허용. 정확 카운트가 필요하면 고해상도/전용 손모델(=모델 교체급, 범위 밖).
- **결론(2026-05-24 problem-solver 재프레이밍으로 정정)**: 시각 트랙의 기본은 **holistic native 평가**(프레임 몇 장+오디오 한 프롬프트로 모델이 시선·태도·제스처를 통째로 질적 평가)다. deliverable이 "풍부한 *질적* 피드백"이고, 그건 native 통째 이해의 영역(north-star). 위 손가락 실험이 보인 다중이미지 binding 한계는 **미세 시간축 시퀀스 복원**에만 적용되는데, 그건 product가 요구하는 신호가 아니다("정밀-프로브 실패 ≠ holistic 부적합" — 혼동 주의). **프레임별 분석+집계는 정밀 시간추적이 하드 요구일 때만의 narrow fallback으로 강등** — 게다가 그 자체가 저수준 feature extraction의 LLM 버전이라 native 원칙과 긴장한다(smart 집계기 스파이크에서 naive 집계는 echo만 함도 확인, 증거 `spike-visual-aggregator.json`). **다음**: 실제 클립에 holistic 평가를 돌려 시선/고개/태도 피드백을 루브릭으로 채점(deliverable 직접 검증).

## D8. native video_url 경로 + 슬라이딩 윈도우 (확정, video_url 스파이크 2026-05-24)

D7이 "다중이미지 frame-dump는 시간축 binding이 깨진다"고 결론낸 뒤, 미검증으로 미뤄둔 **native `video_url` 경로**를 실측했다. 핵심 발견(증거 `spike-native-video.json`, `spike-video-audio.json`, `spike-video-audio-combo.json`):

- **video_url은 시각 시간축 binding을 native로 산다.** 같은 손가락 GT 클립(D7에서 frame-dump가 `0,5,2,0` / `0,0,1,2,3,4,5`로 환각)에서 video_url은 **타임스탬프 박힌 시간순 워크스루**(`00:13 손바닥→00:14 두 손가락→00:26 한 손가락→00:32 양손…`)를 냈다. 정확 *카운트*는 여전히 D7의 fidelity 천장(9/10/4 오독)에 막히지만, **순서·타이밍(=binding)은 살아난다** — frame-dump엔 전혀 없던 것.
- **그러나 vLLM video_url은 시각 전용 — 오디오를 안 넘긴다.** 음성 있는 클립을 video_url 단독으로 보내면 모델이 `"NO AUDIO"`. 같은 클립 오디오를 `audio_url`로 보내면 정확 전사(*"Hello everyone. It's Madhura Roy…"*). 모델 능력(`load_audio_from_video`)과 무관하게 **vLLM 프론트엔드가 비디오에서 오디오 트랙을 버린다**. → "단일 video_url로 AV 동시"는 vLLM에서 불가. **audio_url 별도 필수.**
- **video_url + audio_url 조합은 한 요청에 동작.** HTTP 200, cold TTFT **0.72s**, 출력이 verbal(음성 기반 내용)·vocal(prosody)·visual(시선/자세/시간변화) 세 축을 모두 native로 채움 = D7이 강등한 프레임별+집계 없이 풍부한 종합 평가.
- **프레임 수는 ~32 고정, config로 못 올림.** vLLM `gemma4_mm.py`에 `_VIDEO_MAX_FRAMES = 32`(프레임당 soft 토큰 70) 하드코딩 + `do_sample_frames: False`. 측정 `prompt_tokens=2319`가 **영상 길이 10s~50s 전부 동일** = 길이 무관 ~30프레임. `mm_processor_kwargs`로 상한 못 넘김(넘기면 Gemma 학습 분포 밖이라 비추천).
- **latency 두 축**: ① 모델 prefill은 토큰 고정이라 평평(cold TTFT ~0.58s) ② **wall-clock은 길이 비례로 증가**(10s 0.72s → 풀 50s 1.12s) — 서버측 비디오 **디코딩** 비용. 풀 영상은 목표 0.5s의 2배.
- **Gemma4 native cadence = 2 fps**(메타데이터 `fps: 2.0`). `32프레임 / 2fps = ~16초`가 풀 밀도 윈도우. 50초 통째 = 0.6fps(시간 해상도 묽음), 10초 = 3fps(조밀).

**결론 — 슬라이딩 윈도우 채택:**
- **모달리티별 윈도우**: 비디오 **~16초**(2fps 풀 밀도 + 디코드 ~0.78s 억제), 오디오 **≤30초**(D6).
- **발화 중 점진 처리**: 답변 진행 중 16초 비주얼 윈도우를 도착하는 족족 **독립 추론**해 둔다. 각 윈도우가 독립 평가라 **KV prefix-stability가 불필요**(오디오 레버 A 미스와 무관) — 그래서 비전에서 실효. end-of-turn엔 **마지막 윈도우 + 텍스트 집계만** 남아 지연 최소(D7의 "비전이 streaming의 진짜 자리" 실현).
- **D7 정밀화**: 시각 트랙 기본을 "holistic frame-dump"에서 **`video_url`+`audio_url`(시간축 binding 획득)**로 격상. 프레임별+집계 fallback은 여전히 강등 유지.
- **열린 항목**: 16초 윈도우 경계에서 잘린 제스처 처리, 윈도우 집계 프롬프트 설계, 라이브 캡처/VAD 연동.

> **(2026-05-24 정리)** 아래 표의 스파이크 스크립트는 `legacy/spikes/`로, D5–D8 증거 JSON(`spike-*.json`, `phase3-prefill-effect.json`)은 `legacy/evidence/`로 이동했다. 인덱스 `legacy/README.md`. (현재 모듈 증거 `m2-window-eval`·`m5-e2e`는 `.sisyphus/evidence/`.)

## 신규 코드 (Phase 1 산출물)

| 경로 | 용도 |
|---|---|
| `src/local_infer/native_audio.py` | 베이스라인 복구 + `to_content_part` audio_url 교정 |
| `legacy/spikes/spike_e4b_native_av.py` | 스파이크 probe (스모크 + 풀 배터리) |
| `serving/vllm_e4b_audio.sh` + `Dockerfile.e4b-audio` | E4B+audio 서빙 (image:16,audio:4,video:1) |
| `legacy/spikes/spike_cold_prefill.py` | D6 cold kill-test (오디오 cold 바닥 + confirm) |
| `legacy/spikes/spike_visual_fingers.py` | D7 다중이미지 binding 한계 진단 |
| `legacy/spikes/spike_visual_temporal_v2.py` | D7 프레임별+집계 아키텍처 검증 |
| `legacy/spikes/spike_visual_aggregator.py` | D7 smart 집계기 검증(naive 집계 echo 한계 + 시선/고개 GT 부재) |
| `legacy/spikes/spike_native_video.py` | D8 video_url 시간축 binding kill-test (손가락 GT, 시간순 시퀀스+질적 묘사) |
| `legacy/spikes/spike_video_audio.py` | D8 video_url 단독 → 오디오 native 로드 여부("NO AUDIO" 판정) |

## D4. GPU 위생 규칙

모델 미사용 시 컨테이너 stop + `nvidia-smi`로 VRAM 해제 확인(GPU별 한 자릿수 MiB, util 0%).

## 재사용 가능한 코드 (git 베이스라인 `f80e447`에서 선별 복구)

재시작으로 작업트리에서는 비웠지만, 아래는 깨끗한 재사용 인프라다. Phase 2/3에서 필요 시 `git checkout f80e447 -- <path>`로 의도적으로 되살린다.

| 경로 (베이스라인 기준) | 용도 | 비고 |
|---|---|---|
| `local-infer/src/local_infer/vllm_client.py` | vLLM OpenAI 호환 클라이언트 | 그대로 재사용 |
| `local-infer/src/local_infer/vllm_stream.py` | SSE delta 파서 | 그대로 재사용 |
| `local-infer/src/local_infer/frame_store.py` | 세션별 프레임 버퍼 | 그대로 재사용 |
| `local-infer/src/local_infer/native_media_store.py` | 바운드 MP4 윈도우 파일 스토어 | 그대로 재사용 |
| `local-infer/src/local_infer/native_audio.py` | ffmpeg mono 16kHz WAV 추출 | 30초 클리핑 추가 필요 |
| `local-infer/src/local_infer/native_payloads.py` | 멀티모달 payload 빌더 | **`input_audio`→`audio_url` 교정 필요** |
| `local-infer/tools/probe_gemma4_real_video.py` | 실영상 probe | Phase 1 스파이크로 적응 |
| `sglang/launch-configs/vllm_baseline.sh` | 31B 서빙 config | E4B용 신규 config 작성 시 참고 |

**버린 cruft**(복구 불필요): `audio_analysis.py`, degraded fallback 엔드포인트(`/audio`, `/generate-av-fallback`), "user override native" disclaimer 레이어, "not native success" 방어 문서 더미.
