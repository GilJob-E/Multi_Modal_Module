#!/usr/bin/env bash
# vLLM 기동 (채택된 운영 구성). warm TTFT 0.30s / gen 32 TPS @ 2×RTX4090.
# 이미 vllm-gemma4 컨테이너가 존재하면 그냥 start 하면 됨:
#   docker start vllm-gemma4
# 아래는 처음부터 새로 만들 때의 참조 커맨드.
set -euo pipefail

HF_TOKEN=$(docker inspect vllm-gemma4 --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | grep '^HF_TOKEN=' | head -1 | cut -d= -f2- || echo "$HF_TOKEN")

docker rm -f vllm-gemma4 2>/dev/null || true
docker run -d --name vllm-gemma4 \
  --gpus all --shm-size 64m -p 8000:8000 \
  -v /home/kio/hf_cache:/root/.cache/huggingface \
  -e HF_TOKEN="$HF_TOKEN" \
  vllm/vllm-openai:nightly \
  --model google/gemma-4-31B-it \
  --tensor-parallel-size 2 \
  --max-model-len 4096 \
  --max-num-batched-tokens 8192 \
  --gpu-memory-utilization 0.90 \
  --limit-mm-per-prompt '{"video":1,"image":4}' \
  --dtype bfloat16 \
  --quantization fp8

echo "준비 확인: curl http://localhost:8000/v1/models"
echo "TTFT 측정: cd ~/workspace/gje/video-test && python3 infer_ttft.py sample30.mp4"
