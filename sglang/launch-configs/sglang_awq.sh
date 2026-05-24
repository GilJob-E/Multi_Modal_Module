#!/usr/bin/env bash
# SGLang AWQ 4bit 재시도. 결과: vision_tower compressed-tensors 스킴 미지원으로 기동 실패 (2026-05-20).
# 재시도 조건: PR#25292 (compressed-tensors WNA16 asymmetric weight quant) 머지된 nightly 출시 후.
# 그 땐 메모리 여유 충분(16GB 모델)이라 offload/cuda-graph 끌 필요 없이 정상 성능 기대.
set -euo pipefail

HF_TOKEN=$(docker inspect vllm-gemma4 --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^HF_TOKEN=' | head -1 | cut -d= -f2-)
IMG=lmsysorg/sglang:nightly-dev-cu13-20260520-425dffbd  # ← PR#25292 머지 후 더 최신 nightly로 교체할 것

docker rm -f sglang-gemma4 2>/dev/null || true
docker run -d --name sglang-gemma4 \
  --gpus all --shm-size 32g -p 8001:30000 \
  -v /home/kio/hf_cache:/root/.cache/huggingface \
  -e HF_TOKEN="$HF_TOKEN" \
  -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  --ipc=host \
  "$IMG" \
  python3 -m sglang.launch_server \
    --model-path cyankiwi/gemma-4-31B-it-AWQ-4bit \
    --tp 2 \
    --context-length 4096 \
    --mem-fraction-static 0.85 \
    --host 0.0.0.0 --port 30000

echo "기동 대기: docker logs -f sglang-gemma4"
echo "준비되면: curl http://localhost:8001/v1/models"
