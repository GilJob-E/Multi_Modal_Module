#!/usr/bin/env python3
# pyright: reportAny=false, reportExplicitAny=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportMissingTypeArgument=false, reportUnannotatedClassAttribute=false, reportUnusedCallResult=false
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_PROBES = {
    "english_passphrase": "audio_positive",
    "no_audio_ablation": "no_audio_ablation",
    "beep_only": "beep_only",
    "korean_passphrase": "korean_phrase",
    "av_sync": "av_sync",
    "cross_modal_event": "cross_modal_event",
}
DEFAULT_IMAGE = "vllm/vllm-openai:nightly"
HF_CACHE = "/home/kio/hf_cache"
GJE_ROOT = "/home/kio/workspace/gje"
CONTAINER_GJE_ROOT = "/workspace/gje"
READINESS_TIMEOUT_S = 3600
REFERENCE_CONTAINER = "vllm-gemma4"


@dataclass
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str


class EvidenceLog:
    def __init__(self, path: Path, token: str | None) -> None:
        self.path = path
        self.token = token
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    def sanitize(self, text: str) -> str:
        sanitized = text
        if self.token:
            sanitized = sanitized.replace(self.token, "<HF_TOKEN_REDACTED>")
        sanitized = re.sub(r"HF_TOKEN=[^\s'\"]+", "HF_TOKEN=<HF_TOKEN_REDACTED>", sanitized)
        sanitized = re.sub(r"-e HF_TOKEN=[^\s'\"]+", "-e HF_TOKEN=<HF_TOKEN_REDACTED>", sanitized)
        return sanitized

    def append(self, text: str = "") -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(self.sanitize(text) + "\n")

    def section(self, title: str) -> None:
        self.append(f"\n## {title}")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_command(args: list[str], timeout: int = 120) -> CommandResult:
    completed = subprocess.run(
        args,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    return CommandResult(args, completed.returncode, completed.stdout, completed.stderr)


def sanitize_args(args: list[str], token: str | None) -> list[str]:
    parts: list[str] = []
    for part in args:
        if token and part == token:
            parts.append("<HF_TOKEN_REDACTED>")
        elif token and token in part:
            parts.append(part.replace(token, "<HF_TOKEN_REDACTED>"))
        else:
            parts.append(part)
    return parts


def format_command(args: list[str], token: str | None) -> str:
    return " ".join(sanitize_args(args, token))


def log_command_result(log: EvidenceLog, result: CommandResult) -> None:
    log.append(f"$ {format_command(result.args, log.token)}")
    log.append(f"exit_code={result.returncode}")
    if result.stdout.strip():
        log.append("stdout:")
        log.append(result.stdout.rstrip())
    if result.stderr.strip():
        log.append("stderr:")
        log.append(result.stderr.rstrip())


def model_slug(model: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", model).strip("-").lower()
    return slug or "model"


def gemma_short_name(model: str) -> str:
    lowered = model.lower()
    if "e4b" in lowered:
        return "gemma4-e4b"
    if "e2b" in lowered:
        return "gemma4-e2b"
    return model_slug(model)


def get_hf_token(log: EvidenceLog) -> str:
    token = os.environ.get("HF_TOKEN", "")
    if token:
        log.append("HF_TOKEN source: environment")
        log.token = token
        return token

    result = run_command(
        [
            "docker",
            "inspect",
            REFERENCE_CONTAINER,
            "--format",
            "{{range .Config.Env}}{{println .}}{{end}}",
        ],
        timeout=30,
    )
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            if line.startswith("HF_TOKEN="):
                token = line.split("=", 1)[1]
                log.token = token
                log.append(f"HF_TOKEN source: existing container {REFERENCE_CONTAINER}")
                return token
    log.append("HF_TOKEN source: none found; launching without token may fail on gated models")
    return ""


def select_vllm_image(preferred: str, log: EvidenceLog) -> str:
    result = run_command(["docker", "image", "inspect", preferred], timeout=30)
    if result.returncode == 0:
        log.append(f"vLLM image selected: {preferred}")
        return preferred
    images = run_command(
        ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"], timeout=30
    )
    for image in images.stdout.splitlines():
        if image.startswith("vllm/vllm-openai:"):
            log.append(f"vLLM image selected from local images: {image}")
            return image
    log.append(f"vLLM image selected by default, not currently inspectable: {preferred}")
    return preferred


def docker_env(readiness_timeout_s: int) -> dict[str, str]:
    return {"VLLM_ENGINE_READY_TIMEOUT_S": str(readiness_timeout_s)}


def docker_mounts() -> list[dict[str, str]]:
    return [
        {"host": HF_CACHE, "container": "/root/.cache/huggingface", "mode": "rw"},
        {"host": GJE_ROOT, "container": CONTAINER_GJE_ROOT, "mode": "ro"},
    ]


def docker_run_args(
    container: str,
    model: str,
    port: int,
    image: str,
    hf_token: str,
    readiness_timeout_s: int,
    tensor_parallel_size: int,
) -> list[str]:
    args = [
        "docker",
        "run",
        "-d",
        "--name",
        container,
        "--gpus",
        "all",
        "--ipc=host",
        "--shm-size",
        "16G",
        "-p",
        f"127.0.0.1:{port}:8000",
        "-v",
        f"{HF_CACHE}:/root/.cache/huggingface",
        "-v",
        f"{GJE_ROOT}:{CONTAINER_GJE_ROOT}:ro",
        "-e",
        f"VLLM_ENGINE_READY_TIMEOUT_S={readiness_timeout_s}",
    ]
    if hf_token:
        args.extend(["-e", f"HF_TOKEN={hf_token}"])
    args.extend(
        [
            image,
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "--model",
            model,
            "--tensor-parallel-size",
            str(tensor_parallel_size),
            "--max-model-len",
            "4096",
            "--max-num-batched-tokens",
            "8192",
            "--gpu-memory-utilization",
            "0.90",
            "--limit-mm-per-prompt",
            '{"video":1,"audio":1,"image":4}',
            "--allowed-local-media-path",
            CONTAINER_GJE_ROOT,
            "--dtype",
            "bfloat16",
        ]
    )
    return args


def should_retry_tp2(reason: str) -> bool:
    lowered = reason.casefold()
    retry_terms = [
        "out of memory",
        "cuda oom",
        "torch.cuda.outofmemoryerror",
        "not enough memory",
        "insufficient memory",
        "gpu memory",
        "memory profiling",
        "free memory",
    ]
    return any(term in lowered for term in retry_terms)


def get_json(url: str, timeout: int) -> tuple[int, str]:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except OSError as exc:
        return 0, str(exc)


def wait_for_models(base_url: str, container: str, log: EvidenceLog, timeout_s: int) -> tuple[bool, str]:
    deadline = time.monotonic() + timeout_s
    last_body = "not attempted"
    while time.monotonic() < deadline:
        inspect = run_command(
            ["docker", "inspect", container, "--format", "{{.State.Running}} {{.State.ExitCode}}"],
            timeout=15,
        )
        if inspect.returncode == 0 and inspect.stdout.startswith("false"):
            logs = docker_logs(container, log)
            return False, f"container exited before readiness: {inspect.stdout.strip()}\n{logs[-4000:]}"
        status, body = get_json(f"{base_url.rstrip('/')}/v1/models", timeout=5)
        last_body = body
        if status == 200:
            log.append("readiness /v1/models: HTTP 200")
            log.append(body)
            return True, body
        time.sleep(5)
    logs = docker_logs(container, log)
    return False, f"readiness timeout after {timeout_s}s; last={last_body}\n{logs[-4000:]}"


def docker_logs(container: str, log: EvidenceLog) -> str:
    result = run_command(["docker", "logs", "--tail", "200", container], timeout=60)
    combined = (result.stdout + "\n" + result.stderr).strip()
    if combined:
        log.append(f"docker logs --tail 200 {container}:")
        log.append(combined)
    return combined


def gpu_snapshot() -> dict[str, Any]:
    result = run_command(
        [
            "nvidia-smi",
            "--query-gpu=index,name,memory.used,memory.total,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        timeout=30,
    )
    return {
        "command": result.args,
        "exit_code": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def inspect_vllm_version(image: str) -> dict[str, Any]:
    result = run_command(
        ["docker", "run", "--rm", image, "python3", "-c", "import vllm; print(vllm.__version__)"],
        timeout=120,
    )
    version = result.stdout.strip().splitlines()[-1] if result.returncode == 0 and result.stdout.strip() else None
    return {
        "command": result.args,
        "exit_code": result.returncode,
        "version": version,
        "stderr": result.stderr.strip()[-2000:],
    }


def write_readiness_evidence(path: Path, evidence: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def readiness_evidence_base(
    *,
    model: str,
    container: str,
    command: list[str],
    image: str,
    hf_token: str,
    readiness_timeout_s: int,
    port: int,
    include_runtime_probes: bool,
    tensor_parallel_size: int,
) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "generated_at": utc_now(),
        "model_id": model,
        "container": container,
        "image": image,
        "command": sanitize_args(command, hf_token),
        "command_sanitized": format_command(command, hf_token),
        "mounts": docker_mounts(),
        "env": docker_env(readiness_timeout_s),
        "tensor_parallel_size": tensor_parallel_size,
        "readiness_timeout_s": readiness_timeout_s,
        "base_url": f"http://127.0.0.1:{port}",
        "host_port": f"127.0.0.1:{port}",
        "container_port": 8000,
        "local_media_root": CONTAINER_GJE_ROOT,
        "fixture_uri": f"file://{CONTAINER_GJE_ROOT}/vid_0033.mp4",
        "ipc": "host",
        "shm_size": "16G",
        "classification": "serving_runtime_unresolved",
        "failure_reason": "serving runtime not evaluated yet",
    }
    if include_runtime_probes:
        evidence["gpu_snapshot"] = gpu_snapshot()
        evidence["vllm_version"] = inspect_vllm_version(image)
    else:
        evidence["gpu_snapshot"] = None
        evidence["vllm_version"] = None
    return evidence


def stop_container(container: str, log: EvidenceLog) -> str:
    status_parts: list[str] = []
    inspect = run_command(["docker", "inspect", container], timeout=30)
    if inspect.returncode != 0:
        status = f"container {container} absent before cleanup"
        log.append(status)
        return status
    stop = run_command(["docker", "stop", container], timeout=120)
    log_command_result(log, stop)
    status_parts.append(f"stop_exit={stop.returncode}")
    rm = run_command(["docker", "rm", container], timeout=120)
    log_command_result(log, rm)
    status_parts.append(f"rm_exit={rm.returncode}")
    return ", ".join(status_parts)


def write_no_go(path: Path, entries: list[dict[str, Any]], final_status: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Task 4 Gemma4 vLLM No-Go",
        "",
        f"Generated: {utc_now()}",
        f"Final status: {final_status}",
        "",
    ]
    for entry in entries:
        lines.extend(
            [
                f"## {entry['model']}",
                "",
                f"Status: {entry['status']}",
                f"Container: {entry.get('container', 'n/a')}",
                f"Command: `{entry.get('command', 'n/a')}`",
                f"Reason: {entry.get('reason', 'n/a')}",
                f"Cleanup: {entry.get('cleanup', 'n/a')}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def compact_reason(text: str, max_chars: int = 1800) -> str:
    first_line = text.splitlines()[0] if text.splitlines() else text
    if len(text) <= max_chars:
        return text
    tail_budget = max_chars - len(first_line) - len("\n...\n")
    if tail_budget <= 0:
        return first_line[:max_chars]
    return f"{first_line}\n...\n{text[-tail_budget:]}"


def write_per_model_no_go(no_go_path: Path, entry: dict[str, Any]) -> None:
    short = gemma_short_name(entry["model"])
    path = no_go_path.with_name(f"task-4-{short}-no-go.md")
    write_no_go(path, [entry], f"{short} failed; moving to next candidate when available")


def probe_failure_reason(path: Path, fallback: str) -> tuple[str, dict[str, Any] | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback, None

    summary = data.get("summary", {})
    http_errors = []
    for probe in data.get("probes", []):
        raw = probe.get("raw_response_metadata", {})
        body_text = raw.get("body_text")
        if raw.get("http_status") != 200 and body_text:
            http_errors.append(
                {
                    "probe": probe.get("key"),
                    "http_status": raw.get("http_status"),
                    "body_text": body_text,
                }
            )
    reason_payload = {
        "probe_output": str(path),
        "summary": summary,
        "first_http_error": http_errors[0] if http_errors else None,
        "explicit_audio_transport": "input_audio base64 WAV",
    }
    return json.dumps(reason_payload, ensure_ascii=False), data


def probe_passes(path: Path, model: str, base_url: str) -> tuple[bool, dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    probes = {probe.get("key"): probe for probe in data.get("probes", [])}
    statuses: dict[str, Any] = {}
    all_pass = True
    for fixture_name, alias in REQUIRED_PROBES.items():
        probe = probes.get(fixture_name)
        passed = bool(probe and probe.get("status") == "PASS")
        latency_ok = True
        if fixture_name == "cross_modal_event" and probe:
            latency = probe.get("event_response_latency_ms")
            budget = probe.get("event_response_budget_ms") or 2000
            latency_ok = isinstance(latency, int | float) and latency <= budget
            statuses["event_response_ms"] = latency
            statuses["event_response_budget_ms"] = budget
        statuses[alias] = "PASS" if passed and latency_ok else "FAIL"
        all_pass = all_pass and passed and latency_ok
    data["sequence_summary"] = {
        "selected_model": gemma_short_name(model) if all_pass else None,
        "model": model,
        "base_url": base_url,
        "required_statuses": statuses,
        "all_required_passed": all_pass,
    }
    return all_pass, data


def run_probe(args: argparse.Namespace, model: str, temp_out: Path, log: EvidenceLog) -> CommandResult:
    command = [
        sys.executable,
        "local-infer/tools/probe_native_audio.py",
        "--base-url",
        f"http://localhost:{args.port}",
        "--model",
        model,
        "--fixtures",
        args.fixtures,
        "--out",
        str(temp_out),
    ]
    result = run_command(command, timeout=args.probe_timeout)
    log_command_result(log, result)
    return result


def write_sequence_no_go_json(out_path: Path, entries: list[dict[str, Any]], startup_log: Path, no_go_path: Path) -> None:
    payload = {
        "schema_version": 1,
        "created_by": "local-infer/tools/probe_gemma4_vllm_sequence.py",
        "generated_at": utc_now(),
        "status": "NO_GO",
        "selected_model": None,
        "startup_log": str(startup_log),
        "no_go_out": str(no_go_path),
        "candidate_order": [entry.get("model") for entry in entries],
        "candidates": entries,
        "next_candidate_implication": "Gemma4 E4B and E2B did not pass explicit WAV native audio probes; downstream Task 5 should probe Qwen2.5-Omni.",
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Gemma4 E4B then E2B native audio on local vLLM Docker.")
    parser.add_argument("--models", nargs="+", required=True, help="Model IDs to attempt in order")
    parser.add_argument("--port", type=int, default=8002, help="Host port to bind to localhost")
    parser.add_argument("--fixtures", required=True, help="Fixture directory for probe_native_audio.py")
    parser.add_argument("--out", required=True, help="Successful native probe JSON output")
    parser.add_argument("--no-go-out", required=True, help="No-go markdown output if all candidates fail")
    parser.add_argument("--startup-log", required=True, help="Sanitized startup/probe log output")
    parser.add_argument("--image", default=DEFAULT_IMAGE, help="Local vLLM OpenAI Docker image")
    parser.add_argument("--startup-timeout", type=int, default=READINESS_TIMEOUT_S, help="Seconds to wait for /v1/models")
    parser.add_argument("--probe-timeout", type=int, default=900, help="Seconds to allow probe_native_audio.py")
    parser.add_argument("--readiness-out", default=".sisyphus/evidence/vid0033-gemma4-readiness.json", help="Readiness evidence JSON output")
    parser.add_argument("--dry-run", action="store_true", help="Write launch/readiness evidence without starting Docker")
    args = parser.parse_args()

    if len(args.models) > 2:
        parser.error("Task 4 accepts at most two Gemma4 candidates: E4B first, then E2B")
    if args.models and "e4b" not in args.models[0].casefold():
        parser.error("Task 4 candidate order must try google/gemma-4-E4B-it first")
    if len(args.models) > 1 and "e2b" not in args.models[1].casefold():
        parser.error("Task 4 second candidate must be google/gemma-4-E2B-it")

    startup_log = Path(args.startup_log)
    log = EvidenceLog(startup_log, os.environ.get("HF_TOKEN"))
    log.section("Task 4 Gemma4 vLLM Probe Sequence")
    log.append(f"started_at={utc_now()}")
    log.append(f"models={args.models}")
    log.append(f"port={args.port}")
    log.append("host_bind=127.0.0.1 only")
    log.append(f"fixtures={args.fixtures}")
    log.append(f"readiness_timeout_s={args.startup_timeout}")
    log.append(f"readiness_out={args.readiness_out}")

    hf_token = get_hf_token(log)
    image = select_vllm_image(args.image, log)
    no_go_entries: list[dict[str, Any]] = []
    out_path = Path(args.out)
    no_go_path = Path(args.no_go_out)
    readiness_path = Path(args.readiness_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    for model in args.models:
        short = gemma_short_name(model)
        container = f"vllm-{short}-task4-port{args.port}"
        log.section(f"Candidate {model}")
        entry: dict[str, Any] = {
            "model": model,
            "container": container,
            "started_at": utc_now(),
        }

        ready = False
        readiness = "not attempted"
        evidence: dict[str, Any] | None = None
        for tensor_parallel_size in [1, 2]:
            log.section(f"{model} TP={tensor_parallel_size}")
            run_args = docker_run_args(
                container,
                model,
                args.port,
                image,
                hf_token,
                args.startup_timeout,
                tensor_parallel_size,
            )
            launch_command = format_command(run_args, hf_token)
            log.append(f"launch_command={launch_command}")
            evidence = readiness_evidence_base(
                model=model,
                container=container,
                command=run_args,
                image=image,
                hf_token=hf_token,
                readiness_timeout_s=args.startup_timeout,
                port=args.port,
                include_runtime_probes=not args.dry_run,
                tensor_parallel_size=tensor_parallel_size,
            )
            entry["command"] = log.sanitize(launch_command)
            entry["tensor_parallel_size"] = tensor_parallel_size
            if args.dry_run:
                evidence["dry_run"] = True
                evidence["failure_reason"] = "dry-run did not start serving runtime"
                write_readiness_evidence(readiness_path, evidence)
                log.append(f"dry_run_readiness_evidence={readiness_path}")
                return 0

            preclean = stop_container(container, log)
            log.append(f"prelaunch cleanup for task container: {preclean}")
            started = run_command(run_args, timeout=120)
            log_command_result(log, started)
            if started.returncode != 0:
                failure_reason = (started.stderr or started.stdout).strip()
                readiness = failure_reason
                evidence.update(
                    classification="serving_runtime_unresolved",
                    failure_reason=failure_reason,
                    docker_start={"exit_code": started.returncode, "stdout": started.stdout.strip(), "stderr": started.stderr.strip()},
                    completed_at=utc_now(),
                )
                write_readiness_evidence(readiness_path, evidence)
                entry["cleanup"] = stop_container(container, log)
                if tensor_parallel_size == 1 and should_retry_tp2(failure_reason):
                    log.append("TP=1 startup suggests memory pressure; retrying once with TP=2")
                    continue
                break

            ready, readiness = wait_for_models(f"http://localhost:{args.port}", container, log, args.startup_timeout)
            entry["readiness"] = compact_reason(readiness)
            if ready:
                break

            failure_reason = compact_reason(readiness)
            evidence.update(
                classification="serving_runtime_unresolved",
                failure_reason=failure_reason,
                readiness=readiness,
                completed_at=utc_now(),
            )
            write_readiness_evidence(readiness_path, evidence)
            entry["cleanup"] = stop_container(container, log)
            if tensor_parallel_size == 1 and should_retry_tp2(failure_reason):
                log.append("TP=1 readiness failure suggests memory pressure; retrying once with TP=2")
                continue
            break

        entry["readiness"] = compact_reason(readiness)
        if not ready:
            failure_reason = compact_reason(readiness)
            entry.update(status="serving_runtime_unresolved", reason=failure_reason)
            if evidence is not None:
                evidence.update(
                    classification="serving_runtime_unresolved",
                    failure_reason=failure_reason,
                    readiness=readiness,
                    completed_at=utc_now(),
                )
                write_readiness_evidence(readiness_path, evidence)
            entry["cleanup"] = stop_container(container, log)
            no_go_entries.append(entry)
            write_per_model_no_go(no_go_path, entry)
            continue

        if evidence is not None:
            evidence.update(classification="ready", failure_reason="", readiness=readiness, completed_at=utc_now())
            write_readiness_evidence(readiness_path, evidence)

        temp_out = out_path.with_name(f"task-4-{short}-probe-raw.json")
        probe_result = run_probe(args, model, temp_out, log)
        if probe_result.returncode != 0:
            reason, raw_probe = probe_failure_reason(
                temp_out,
                (probe_result.stderr or probe_result.stdout or "probe exited non-zero").strip()[-2000:],
            )
            entry.update(
                status="probe-no-go",
                reason=reason,
                raw_probe_output=str(temp_out),
            )
            if raw_probe is not None:
                entry["probe_summary"] = raw_probe.get("summary")
            entry["cleanup"] = stop_container(container, log)
            no_go_entries.append(entry)
            write_per_model_no_go(no_go_path, entry)
            continue

        try:
            passed, final_json = probe_passes(temp_out, model, f"http://localhost:{args.port}")
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            entry.update(status="probe-output-invalid", reason=str(exc))
            entry["cleanup"] = stop_container(container, log)
            no_go_entries.append(entry)
            write_per_model_no_go(no_go_path, entry)
            continue

        entry["cleanup"] = stop_container(container, log)
        if passed:
            final_json["sequence_summary"]["startup_log"] = str(startup_log)
            final_json["sequence_summary"]["container_cleanup"] = entry["cleanup"]
            final_json["sequence_summary"]["selected_model"] = short
            out_path.write_text(json.dumps(final_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            log.append(f"selected_model={short}")
            log.append("result=PASS; task container stopped after evidence capture")
            return 0

        entry.update(status="probe-no-go", reason=json.dumps(final_json["sequence_summary"], ensure_ascii=False))
        no_go_entries.append(entry)
        write_per_model_no_go(no_go_path, entry)

    write_no_go(no_go_path, no_go_entries, "all Gemma4 vLLM candidates failed")
    write_sequence_no_go_json(out_path, no_go_entries, startup_log, no_go_path)
    log.append("result=NO-GO; all task containers stopped or absent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
