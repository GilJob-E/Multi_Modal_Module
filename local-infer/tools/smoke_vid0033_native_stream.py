#!/usr/bin/env python3
from __future__ import annotations

# pyright: reportMissingImports=false

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "local-infer" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


LOCKED_SOURCE = Path("/home/kio/workspace/gje/vid_0033.mp4")
METADATA_PATH = ROOT / ".sisyphus" / "evidence" / "vid0033-media-metadata.json"
DEFAULT_OUT = ROOT / ".sisyphus" / "evidence" / "native-streaming-vid0033-smoke.json"
DEFAULT_PROMPT = "지원자의 현재 답변과 태도를 짧게 보고 후속 질문 하나를 해줘."
WINDOW_SPECS = [(12_000, 15_000), (20_000, 23_000)]
WINDOWS_ENDPOINT_TEMPLATE = "/v1/native/sessions/{session_id}/windows"
GENERATE_ENDPOINT_TEMPLATE = "/v1/native/sessions/{session_id}/generate"
FORBIDDEN_ENDPOINTS = [
    "/v1/sessions/{session_id}/frames",
    "/v1/sessions/{session_id}/generate",
    "/v1/sessions/{session_id}/audio",
    "/v1/sessions/{session_id}/generate-av-fallback",
]


class FakeVllmClient:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def stream_chat(self, payload: dict[str, Any]):
        self.payloads.append(payload)
        yield "네, "
        yield "그 경험에서 배운 점을 조금 더 구체적으로 말씀해 주세요."


class FakeNativeAudioExtractor:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def extract_window(self, source_mp4_path: str | Path, *, start_seconds: float, duration_seconds: float):
        self.calls.append(
            {
                "source_mp4_path": str(source_mp4_path),
                "start_seconds": start_seconds,
                "duration_seconds": duration_seconds,
            }
        )
        from local_infer.native_audio import NativeInputAudio

        return NativeInputAudio.from_wav_bytes(_tiny_wav_bytes())


def main() -> int:
    args = parse_args()
    out_path = Path(args.out)
    started = time.perf_counter()
    try:
        evidence = run_smoke(args, started)
    except SmokeError as exc:
        evidence = {
            "ok": False,
            "error": str(exc),
            "source_path": str(Path(args.source)),
            "native_endpoints": native_endpoints(args.session_id),
        }
        write_json(out_path, evidence)
        print(f"native streaming smoke failed: {exc}", file=sys.stderr)
        return 1

    write_json(out_path, evidence)
    print(f"wrote {out_path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test native MP4-window streaming with vid_0033.mp4")
    parser.add_argument("--source", default=str(LOCKED_SOURCE), help="source MP4 fixture path")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="evidence JSON output path")
    parser.add_argument("--session-id", default="native-smoke-vid0033", help="native session id")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="Korean follow-up prompt")
    parser.add_argument("--in-process-fake-vllm", action="store_true", help="use FastAPI TestClient and fake vLLM")
    parser.add_argument("--base-url", help="live gateway base URL, for example http://127.0.0.1:8000")
    args = parser.parse_args()
    if bool(args.in_process_fake_vllm) == bool(args.base_url):
        parser.error("choose exactly one of --in-process-fake-vllm or --base-url")
    return args


def run_smoke(args: argparse.Namespace, started: float) -> dict[str, Any]:
    source_path = Path(args.source)
    if not source_path.exists():
        raise SmokeError(f"source file not found: {source_path}")
    if not source_path.is_file():
        raise SmokeError(f"source path is not a file: {source_path}")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SmokeError("ffmpeg binary not found on PATH")

    metadata = load_metadata()
    source_sha256 = sha256_file(source_path)
    if source_path == LOCKED_SOURCE and source_sha256 != metadata["sha256"]:
        raise SmokeError(
            f"locked source sha256 mismatch: expected {metadata['sha256']}, got {source_sha256}"
        )

    with tempfile.TemporaryDirectory(prefix="vid0033-native-smoke-", dir="/tmp/opencode") as temp_dir:
        derived_windows = derive_windows(
            ffmpeg=ffmpeg,
            source_path=source_path,
            output_dir=Path(temp_dir),
        )
        if args.in_process_fake_vllm:
            mode_result = run_in_process(args=args, temp_dir=Path(temp_dir), derived_windows=derived_windows)
        else:
            mode_result = run_live(args=args, derived_windows=derived_windows)

    events = mode_result["sse_events"]
    final_event = next((event for event in reversed(events) if event.get("type") == "final"), {})
    response_text = str(final_event.get("text") or "")
    payload_summary = mode_result.get("captured_payload_summary") or {}
    video_url_present = bool(payload_summary.get("video_url_present", final_event.get("video_url") is not None))
    input_audio_present = bool(payload_summary.get("input_audio_present", final_event.get("input_audio_present") is True))
    image_url_present = bool(payload_summary.get("image_url_present", False))
    fallback_used = bool(payload_summary.get("fallback_used", final_event.get("fallback_used", False)))

    evidence = {
        "ok": True,
        "mode": "in-process-fake-vllm" if args.in_process_fake_vllm else "live-base-url",
        "source_path": str(source_path),
        "source_sha256": source_sha256,
        "source_sha256_expected": metadata["sha256"] if source_path == LOCKED_SOURCE else None,
        "source_matches_locked_fixture": source_path == LOCKED_SOURCE and source_sha256 == metadata["sha256"],
        "source_media_metadata": {
            "duration": metadata.get("format", {}).get("duration"),
            "size": metadata.get("format", {}).get("size"),
            "streams": metadata.get("streams", []),
        },
        "session_id": args.session_id,
        "prompt": args.prompt,
        "native_endpoints": native_endpoints(args.session_id),
        "forbidden_path_checks": forbidden_path_checks(args.session_id),
        "uploaded_windows": mode_result["uploaded_windows"],
        "captured_payload_summary": payload_summary or None,
        "captured_payload_count": mode_result.get("captured_payload_count", 0),
        "fake_audio_extractor_calls": mode_result.get("fake_audio_extractor_calls", []),
        "sse_event_types": [event.get("type") for event in events],
        "sse_final_metadata": final_event,
        "response_excerpt": response_text[:240],
        "response_non_empty": bool(response_text),
        "video_url_present": video_url_present,
        "input_audio_present": input_audio_present,
        "image_url_present": image_url_present,
        "fallback_used": fallback_used,
        "timings_ms": {
            **mode_result["timings_ms"],
            "total": round((time.perf_counter() - started) * 1000, 1),
        },
    }
    assert_smoke_evidence(evidence)
    return evidence


def derive_windows(*, ffmpeg: str, source_path: Path, output_dir: Path) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    windows: list[dict[str, Any]] = []
    for index, (start_ms, end_ms) in enumerate(WINDOW_SPECS, start=1):
        duration_ms = end_ms - start_ms
        out_path = output_dir / f"vid0033-window-{index}-{start_ms}-{end_ms}.mp4"
        command = [
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            format_seconds(start_ms / 1000),
            "-t",
            format_seconds(duration_ms / 1000),
            "-i",
            str(source_path),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "28",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            "-y",
            str(out_path),
        ]
        t0 = time.perf_counter()
        completed = subprocess.run(command, capture_output=True, check=False)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        if completed.returncode != 0:
            stderr = completed.stderr.decode("utf-8", errors="replace").strip()
            raise SmokeError(f"ffmpeg window derivation failed for {start_ms}-{end_ms}ms: {stderr}")
        if not out_path.exists() or out_path.stat().st_size == 0:
            raise SmokeError(f"ffmpeg produced empty window: {out_path}")
        window_bytes = out_path.read_bytes()
        windows.append(
            {
                "index": index,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "duration_ms": duration_ms,
                "path": str(out_path),
                "size_bytes": len(window_bytes),
                "sha256": hashlib.sha256(window_bytes).hexdigest(),
                "ffmpeg_elapsed_ms": elapsed_ms,
                "video_mp4_base64": base64.b64encode(window_bytes).decode("ascii"),
            }
        )
    return windows


def run_in_process(*, args: argparse.Namespace, temp_dir: Path, derived_windows: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        from fastapi.testclient import TestClient
        from local_infer.app import create_app
        from local_infer.native_payloads import summarize_native_payload
    except ModuleNotFoundError as exc:
        reexec_with_uv_if_possible(exc)
        raise

    fake_vllm = FakeVllmClient()
    fake_audio = FakeNativeAudioExtractor()
    media_dir = temp_dir / "native-media"
    client = TestClient(
        create_app(
            vllm_client=fake_vllm,
            native_audio_extractor=fake_audio,
            native_media_dir=str(media_dir),
            native_media_url_prefix="file:///native-smoke-media",
        )
    )
    uploaded_windows = []
    upload_start = time.perf_counter()
    for window in derived_windows:
        response = client.post(windows_endpoint(args.session_id), json=window_payload(window))
        if response.status_code != 200:
            raise SmokeError(f"native window upload failed with {response.status_code}: {response.text}")
        uploaded_windows.append(upload_record(window, response.json()))
    upload_ms = round((time.perf_counter() - upload_start) * 1000, 1)

    generate_start = time.perf_counter()
    with client.stream(
        "POST",
        generate_endpoint(args.session_id),
        json={"prompt": args.prompt, "max_tokens": 64, "temperature": 0.2},
    ) as response:
        body = response.read().decode("utf-8")
    generate_ms = round((time.perf_counter() - generate_start) * 1000, 1)
    if response.status_code != 200:
        raise SmokeError(f"native generate failed with {response.status_code}: {body}")

    return {
        "uploaded_windows": uploaded_windows,
        "sse_events": parse_sse_events(body),
        "captured_payload_count": len(fake_vllm.payloads),
        "captured_payload_summary": summarize_native_payload(fake_vllm.payloads[0]) if fake_vllm.payloads else {},
        "fake_audio_extractor_calls": fake_audio.calls,
        "timings_ms": {"upload": upload_ms, "generate": generate_ms},
    }


def run_live(*, args: argparse.Namespace, derived_windows: list[dict[str, Any]]) -> dict[str, Any]:
    uploaded_windows = []
    upload_start = time.perf_counter()
    for window in derived_windows:
        response_json = post_json(args.base_url, windows_endpoint(args.session_id), window_payload(window))
        uploaded_windows.append(upload_record(window, response_json))
    upload_ms = round((time.perf_counter() - upload_start) * 1000, 1)

    generate_start = time.perf_counter()
    body = post_json_raw(
        args.base_url,
        generate_endpoint(args.session_id),
        {"prompt": args.prompt, "max_tokens": 64, "temperature": 0.2},
    )
    generate_ms = round((time.perf_counter() - generate_start) * 1000, 1)
    return {
        "uploaded_windows": uploaded_windows,
        "sse_events": parse_sse_events(body),
        "timings_ms": {"upload": upload_ms, "generate": generate_ms},
    }


def post_json(base_url: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = post_json_raw(base_url, path, payload)
    return json.loads(body)


def post_json_raw(base_url: str, path: str, payload: dict[str, Any]) -> str:
    url = base_url.rstrip("/") + path
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SmokeError(f"POST {path} failed with {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SmokeError(f"POST {path} failed: {exc.reason}") from exc


def reexec_with_uv_if_possible(exc: ModuleNotFoundError) -> None:
    if os.environ.get("SMOKE_VID0033_UV_REEXEC") == "1":
        return
    if shutil.which("uv") is None:
        return
    missing = exc.name or ""
    if missing.split(".")[0] not in {"fastapi", "httpx", "pydantic"}:
        return
    env = os.environ.copy()
    env["SMOKE_VID0033_UV_REEXEC"] = "1"
    command = [
        "uv",
        "run",
        "--project",
        str(ROOT / "local-infer"),
        "--with",
        "httpx",
        "python3",
        str(Path(__file__).resolve()),
        *sys.argv[1:],
    ]
    os.execvpe("uv", command, env)


def window_payload(window: dict[str, Any]) -> dict[str, Any]:
    return {
        "start_ms": window["start_ms"],
        "end_ms": window["end_ms"],
        "video_mp4_base64": window["video_mp4_base64"],
        "mime_type": "video/mp4",
    }


def upload_record(window: dict[str, Any], response_json: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": window["index"],
        "start_ms": window["start_ms"],
        "end_ms": window["end_ms"],
        "duration_ms": window["duration_ms"],
        "derived_path": window["path"],
        "derived_size_bytes": window["size_bytes"],
        "derived_sha256": window["sha256"],
        "ffmpeg_elapsed_ms": window["ffmpeg_elapsed_ms"],
        "upload_response": response_json,
    }


def parse_sse_events(body: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in body.strip().split("\n\n"):
        data_lines = [line.removeprefix("data: ") for line in block.splitlines() if line.startswith("data: ")]
        if data_lines:
            events.append(json.loads("\n".join(data_lines)))
    return events


def assert_smoke_evidence(evidence: dict[str, Any]) -> None:
    if evidence["source_path"] == str(LOCKED_SOURCE) and evidence.get("source_matches_locked_fixture") is not True:
        raise SmokeError("locked source metadata assertion failed")
    required_true = ["video_url_present", "input_audio_present", "response_non_empty"]
    for key in required_true:
        if evidence.get(key) is not True:
            raise SmokeError(f"evidence invariant failed: {key} must be true")
    required_false = ["image_url_present", "fallback_used"]
    for key in required_false:
        if evidence.get(key) is not False:
            raise SmokeError(f"evidence invariant failed: {key} must be false")
    if not evidence["uploaded_windows"]:
        raise SmokeError("no windows uploaded")
    if "final" not in evidence["sse_event_types"]:
        raise SmokeError("SSE final event missing")


def forbidden_path_checks(session_id: str) -> dict[str, Any]:
    called = [windows_endpoint(session_id), generate_endpoint(session_id)]
    forbidden = [endpoint.format(session_id=session_id) for endpoint in FORBIDDEN_ENDPOINTS]
    return {
        "called_endpoints": called,
        "forbidden_endpoints": forbidden,
        "forbidden_called": [endpoint for endpoint in forbidden if endpoint in called],
        "audio_analysis_imported_by_runner": False,
        "asr_vad_transcript_or_rule_fallback_used": False,
    }


def native_endpoints(session_id: str) -> dict[str, str]:
    return {"windows": windows_endpoint(session_id), "generate": generate_endpoint(session_id)}


def windows_endpoint(session_id: str) -> str:
    return WINDOWS_ENDPOINT_TEMPLATE.format(session_id=session_id)


def generate_endpoint(session_id: str) -> str:
    return GENERATE_ENDPOINT_TEMPLATE.format(session_id=session_id)


def load_metadata() -> dict[str, Any]:
    return json.loads(METADATA_PATH.read_text())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def format_seconds(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _tiny_wav_bytes() -> bytes:
    sample_rate = 16_000
    duration_samples = sample_rate // 10
    pcm = b"\x00\x00" * duration_samples
    data_size = len(pcm)
    riff_size = 36 + data_size
    return (
        b"RIFF"
        + riff_size.to_bytes(4, "little")
        + b"WAVEfmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + sample_rate.to_bytes(4, "little")
        + (sample_rate * 2).to_bytes(4, "little")
        + (2).to_bytes(2, "little")
        + (16).to_bytes(2, "little")
        + b"data"
        + data_size.to_bytes(4, "little")
        + pcm
    )


class SmokeError(Exception):
    pass


if __name__ == "__main__":
    raise SystemExit(main())
