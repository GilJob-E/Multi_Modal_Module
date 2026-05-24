#!/usr/bin/env bash
# SGLang fp8 재시도 (동일 모델). 결과: 기동되나 OOM/1~5TPS로 실사용 불가 (2026-05-20).
# fp8 triton assert fix(PR#25286) 포함 빌드 사용. PR#25292 머지 후 AWQ 쪽 재시도 권장.
set -euo pipefail

HF_TOKEN=$(docker inspect vllm-gemma4 --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^HF_TOKEN=' | head -1 | cut -d= -f2-)
IMG=lmsysorg/sglang:nightly-dev-cu13-20260520-425dffbd

docker rm -f sglang-gemma4 2>/dev/null || true
docker run -d --name sglang-gemma4 \
  --gpus all --shm-size 32g -p 8001:30000 \
  -v /home/kio/hf_cache:/root/.cache/huggingface \
  -e HF_TOKEN="$HF_TOKEN" \
  -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  --ipc=host \
  "$IMG" \
  python3 -m sglang.launch_server \
    --model-path google/gemma-4-31B-it \
    --tp 2 --quantization fp8 \
    --context-length 4096 \
    --mem-fraction-static 0.70 \
    --cpu-offload-gb 18 \
    --disable-cuda-graph \
    --host 0.0.0.0 --port 30000

echo "기동 대기: docker logs -f sglang-gemma4"
echo "준비되면: curl http://localhost:8001/v1/models"
