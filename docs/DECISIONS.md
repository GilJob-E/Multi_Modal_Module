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
- warm TTFT 0.03–0.38s. 동일 오디오 prefix가 요청 간 캐시 재사용됨(2번째 호출 0.03s) → **periodic prefill 실효성 직접 입증**.
- 서빙: 파생 이미지 `vllm-gemma4-audio:local`(nightly + librosa/soundfile), E4B 단일 GPU ~22.7GB, `--limit-mm-per-prompt '{"image":4,"audio":1}' --enable-prefix-caching`.

## 신규 코드 (Phase 1 산출물)

| 경로 | 용도 |
|---|---|
| `src/local_infer/native_audio.py` | 베이스라인 복구 + `to_content_part` audio_url 교정 |
| `tools/spike_e4b_native_av.py` | 스파이크 probe (스모크 + 풀 배터리) |
| `sglang/launch-configs/vllm_e4b_audio.sh` + `Dockerfile.e4b-audio` | E4B+audio 서빙 |

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
