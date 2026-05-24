# SGLang vs vLLM 평가 기록 — Gemma 4 실시간 화상챗 추론

**날짜:** 2026-05-20
**목적:** `google/gemma-4-31B-it`(멀티모달, 영상+음성+텍스트→텍스트 스트리밍)를 실시간 면접 시스템 추론에 쓸 때, 현재 vLLM 대신 SGLang으로 옮기는 게 나은지 검증.
**결론:** ❌ **No-Go. vLLM 유지.** (근거는 아래)

---

## 하드웨어 / 환경
- GPU: RTX 4090 × 2 (각 24GB, Ada/sm_89), driver 595, CUDA 13 호환
- 모델 캐시: `~/hf_cache/`
- 비디오 테스트 스크립트: `~/workspace/gje/video-test/{infer.py, infer_ttft.py}` (OpenAI chat completions API에 base64 video 전송, TTFT/TPS 측정)
- 샘플: `sample30.mp4` (3.2MB, 30초)

---

## 단계별 결과

### 1단계 — vLLM 베이스라인 ✅ (성공)
- 이미지: `vllm/vllm-openai:nightly` (v0.20.2rc1)
- 모델: `google/gemma-4-31B-it` 원본 bf16(59GB) + **online fp8** 양자화
- 옵션: `--tp 2 --quantization fp8 --max-model-len 4096 --max-num-batched-tokens 8192 --gpu-memory-utilization 0.90 --dtype bfloat16 --limit-mm-per-prompt {video:1,image:4}`
- 콜드스타트 ~3분 40초, GPU당 ~22.4GB 점유 (24GB에 깔끔히 적재)
- **측정 (sample30.mp4 비디오 추론):**
  - Cold TTFT: **7.50s** / total 15.4s / gen **32.3 TPS**
  - Warm TTFT: **0.30s** / total 8.2s / gen **32.5 TPS** ← prefix cache hit
- → 실시간 화상챗에 충분히 좋은 베이스라인.

### 2단계 — SGLang fp8 (동일 모델, 공정 비교) ❌
- 이미지 시도 1: `lmsysorg/sglang:latest` (5/17 빌드, 47GB)
  - **fp8 triton 커널 assert로 첫 추론 즉사**: `triton_scaled_mm: assert scale_b.shape[1]==1 ...`
  - 원인 = **PR #25286 "[Gemma4] Fix FP8 Triton scale layout"** (2026-05-19 21:00 UTC merge). latest엔 미포함.
- 이미지 시도 2: `lmsysorg/sglang:nightly-dev-cu13-20260520-425dffbd` (fix 포함 빌드, 13GB)
  - ✅ **fp8 assert 해소 확인** — 텍스트 prefill 정상 진입 (fix 작동 검증됨)
  - ❌ 하지만 메모리 한계:
    - offload 없음 → 로딩/추론 OOM (forward용 3GB 할당 실패, free 44MiB까지 떨어짐)
    - `--cpu-offload-gb 18` → 기동되나 **1~5 tok/s**로 실사용 불가 (CPU↔GPU weight swap)
  - 근본 원인: SGLang의 Gemma4 online-fp8 경로가 bf16을 GPU에 materialize 후 변환 → 로딩 피크가 vLLM(레이어별 스트리밍)보다 큼. 31B+TP=2가 24GB×2에 추론 헤드룸 없이 빠듯하게만 적재됨.

### 3단계 — SGLang AWQ 4bit (다른 모델, 메모리 우회 시도) ❌
- 모델: `cyankiwi/gemma-4-31B-it-AWQ-4bit` (16GB, 멀티모달 보존, compressed-tensors pack-quantized int4 group, vision tower 192레이어는 ignore=비양자화)
- offload 없이 GPU에 통째 적재 가능한 사이즈라 정공법.
- ❌ 기동 실패: **`NotImplementedError: No compressed-tensors compatible scheme was found`** @ `gemma4_vision.py` qkv
  - vision tower의 `ClippableQKVParallelLinear` 명명이 compressed-tensors `ignore` 매칭과 불일치 → vision qkv를 양자화 대상으로 오인
  - GitHub: **PR #25292 "[Quant] Support asymmetric weight quant in compressed-tensors WNA16" 가 아직 open** → AWQ Gemma4 경로 SGLang 미완성 확인
  - 우회 시도 (`--language-only`, `--disable-multimodal`, `--enable-multimodal false`) 전부 불가 (플래그 부재/부적합). 코드 레벨 버그.

---

## 왜 vLLM은 되고 SGLang은 실패했나 (요약)
- **fp8 (동일 모델):** 둘 다 "31B를 24GB×2에 욱여넣는" 같은 벽에 부딪힘. vLLM은 레이어별 스트리밍 변환 + 타이트한 메모리 회계로 가까스로 통과(헤드룸 확보), SGLang은 로딩 피크/활성 메모리 오버헤드가 더 커서 넘침. **SGLang이 나빠서가 아니라 이 모델+GPU 조합의 여유가 SGLang 오버헤드를 못 받아준 것.**
- **AWQ (다른 모델):** 메모리는 해결됐지만 SGLang의 Gemma4 vision tower가 compressed-tensors 스킴을 아직 못 읽음 (PR #25292 머지 대기). 별개의 미구현 기능 문제.

---

## 재시도 트리거 (둘 중 하나 충족 시 재평가)
1. **PR #25292 머지된 SGLang nightly 출시** → AWQ 4bit 모델로 재시도 (가장 유망, 메모리 여유). 모델/이미지 이미 받아둠.
2. GPU를 메모리 큰 카드(A6000 48GB / H100)로 교체 → fp8 경로 즉시 열림.

---

## 남긴 자산 (재현용)
- AWQ 모델 캐시: `~/hf_cache/hub/models--cyankiwi--gemma-4-31B-it-AWQ-4bit` (20GB)
- 원본 모델 캐시: `~/hf_cache/hub/models--google--gemma-4-31B-it` (59GB)
- SGLang Docker 이미지:
  - `lmsysorg/sglang:latest` (47GB, 5/17 빌드, fp8 fix 미포함)
  - `lmsysorg/sglang:nightly-dev-cu13-20260520-425dffbd` (13GB, fp8 fix 포함)
- 재현용 launch 커맨드: `launch-configs/` 참조
- vLLM 컨테이너: `vllm-gemma4` (Exited 보존). `docker start vllm-gemma4`로 0.3s TTFT 복귀.

## GPU 위생
모든 단계 종료 후 컨테이너 제거 + nvidia-smi 확인 → GPU0 9MiB / GPU1 1MiB, util 0%.
