#!/usr/bin/env bash
# Gemma 4 E4B + native audio 서빙.
# E4B는 작아 단일 GPU(TP 불필요). 오디오 의존성은 파생 이미지(Dockerfile.e4b-audio)로 보강.
# audio=4: cold kill-test 레버 A([chunk1,chunk2] 다중 audio_url 파트 전송)와
#          향후 청크 점진 캐싱을 위해 audio 슬롯 ≥2 필요(이전 Phase1은 audio=1).
# 종료: docker stop vllm-gemma4-e4b  (GPU 위생: 이후 nvidia-smi로 VRAM 해제 확인)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="vllm-gemma4-audio:local"
NAME="vllm-gemma4-e4b"

# 1) 오디오 의존성 얹은 파생 이미지 빌드(없을 때만)
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "[build] $IMAGE (librosa, soundfile)…"
  docker build -t "$IMAGE" -f "$HERE/Dockerfile.e4b-audio" "$HERE"
fi

# 2) 컨테이너 기동
docker rm -f "$NAME" 2>/dev/null || true
docker run -d --name "$NAME" \
  --gpus all --shm-size 64m -p 8000:8000 \
  -v /home/kio/hf_cache:/root/.cache/huggingface \
  -v /home/kio/workspace/gje:/workspace/gje \
  -e HF_TOKEN="${HF_TOKEN:?HF_TOKEN must be set}" \
  "$IMAGE" \
  --model google/gemma-4-E4B-it \
  --max-model-len 8192 \
  --limit-mm-per-prompt '{"image":16,"audio":4}' \
  --enable-prefix-caching \
  --dtype bfloat16

echo "준비 확인: curl -s http://localhost:8000/v1/models | jq .data[].id"
echo "로그:      docker logs -f $NAME"
