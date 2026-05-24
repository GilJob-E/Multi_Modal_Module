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
- **결론**: 시각 트랙은 프레임 덤프 대신 프레임별+집계로 설계. 집계기는 (t,count/caption) 타임라인을 LLM에 줘 질적 시간동역학을 묘사하는 방향(미구현, 다음 작업).

## 신규 코드 (Phase 1 산출물)

| 경로 | 용도 |
|---|---|
| `src/local_infer/native_audio.py` | 베이스라인 복구 + `to_content_part` audio_url 교정 |
| `tools/spike_e4b_native_av.py` | 스파이크 probe (스모크 + 풀 배터리) |
| `sglang/launch-configs/vllm_e4b_audio.sh` + `Dockerfile.e4b-audio` | E4B+audio 서빙 (image:16,audio:4) |
| `tools/spike_cold_prefill.py` | D6 cold kill-test (오디오 cold 바닥 + confirm) |
| `tools/spike_visual_fingers.py` | D7 다중이미지 binding 한계 진단 |
| `tools/spike_visual_temporal_v2.py` | D7 프레임별+집계 아키텍처 검증 |

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
