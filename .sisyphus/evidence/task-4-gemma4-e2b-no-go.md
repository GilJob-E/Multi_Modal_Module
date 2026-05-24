# Task 4 Gemma4 vLLM No-Go

Generated: 2026-05-22T05:25:04.230544+00:00
Final status: gemma4-e2b failed; moving to next candidate when available

## google/gemma-4-E2B-it

Status: probe-no-go
Container: vllm-gemma4-e2b-task4-port8002
Command: `docker run -d --name vllm-gemma4-e2b-task4-port8002 --gpus all --ipc=host --shm-size 16G -p 127.0.0.1:8002:8000 -v /home/kio/hf_cache:/root/.cache/huggingface -v /home/kio/workspace/gje:/workspace/gje:ro -e VLLM_ENGINE_READY_TIMEOUT_S=3600 -e HF_TOKEN=<HF_TOKEN_REDACTED> vllm/vllm-openai:nightly --host 0.0.0.0 --port 8000 --model google/gemma-4-E2B-it --tensor-parallel-size 1 --max-model-len 4096 --max-num-batched-tokens 8192 --gpu-memory-utilization 0.90 --limit-mm-per-prompt {"video":1,"audio":1,"image":4} --allowed-local-media-path /workspace/gje --dtype bfloat16`
Reason: {"probe_output": ".sisyphus/evidence/task-4-gemma4-e2b-probe-raw.json", "summary": {"status": "FAIL", "probe_statuses": {"english_passphrase": "FAIL", "korean_passphrase": "FAIL", "no_audio_ablation": "FAIL", "beep_only": "FAIL", "av_sync": "FAIL", "cross_modal_event": "FAIL"}, "expect_no_audio": false, "event_response_ms": 15.0, "event_response_budget_ms": 2000}, "first_http_error": {"probe": "english_passphrase", "http_status": 400, "body_text": "{\"error\":{\"message\":\"Invalid or unsupported audio file.\",\"type\":\"BadRequestError\",\"param\":null,\"code\":400}}"}, "explicit_audio_transport": "input_audio base64 WAV"}
Cleanup: stop_exit=0, rm_exit=0
