# pyright: reportMissingImports=false
import base64
import subprocess
from pathlib import Path

import pytest

import local_infer.native_audio as native_audio
from local_infer.native_audio import NativeAudioExtractor, NativeInputAudio


def test_native_input_audio_encodes_wav_bytes_as_base64_transport():
    audio = NativeInputAudio.from_wav_bytes(b"RIFFwav-bytes")

    assert audio.format == "wav"
    assert audio.data == base64.b64encode(b"RIFFwav-bytes").decode("ascii")
    assert audio.to_content_part() == {
        "type": "input_audio",
        "input_audio": {"data": audio.data, "format": "wav"},
    }


def test_extract_window_requests_mono_16khz_pcm_wav_from_source_mp4(monkeypatch):
    calls = []

    def fake_run(command, *, capture_output, check, timeout):
        calls.append((command, capture_output, check, timeout))
        return subprocess.CompletedProcess(command, 0, stdout=b"RIFFwav", stderr=b"")

    monkeypatch.setattr(native_audio.subprocess, "run", fake_run)

    audio = NativeAudioExtractor(ffmpeg_binary="/opt/ffmpeg", timeout_seconds=3).extract_window(
        Path("/tmp/uploaded.mp4"),
        start_seconds=12.5,
        duration_seconds=2.25,
    )

    command, capture_output, check, timeout = calls[0]
    assert audio == NativeInputAudio(data=base64.b64encode(b"RIFFwav").decode("ascii"))
    assert capture_output is True
    assert check is False
    assert timeout == 3
    assert command == [
        "/opt/ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        "12.5",
        "-t",
        "2.25",
        "-i",
        "/tmp/uploaded.mp4",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-acodec",
        "pcm_s16le",
        "-f",
        "wav",
        "pipe:1",
    ]


def test_extract_window_fails_closed_when_ffmpeg_binary_is_missing(monkeypatch):
    def fake_run(command, **_kwargs):
        raise FileNotFoundError(command[0])

    monkeypatch.setattr(native_audio.subprocess, "run", fake_run)

    with pytest.raises(ValueError, match="ffmpeg binary not found"):
        NativeAudioExtractor(ffmpeg_binary="missing-ffmpeg").extract_window(
            "uploaded.mp4",
            start_seconds=0,
            duration_seconds=1,
        )


def test_extract_window_fails_closed_on_timeout(monkeypatch):
    def fake_run(command, **_kwargs):
        timeout = _kwargs["timeout"]
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(native_audio.subprocess, "run", fake_run)

    with pytest.raises(ValueError, match="ffmpeg timed out"):
        NativeAudioExtractor(timeout_seconds=0.25).extract_window("uploaded.mp4", start_seconds=0, duration_seconds=1)


def test_extract_window_fails_closed_on_nonzero_exit(monkeypatch):
    def fake_run(command, **_kwargs):
        return subprocess.CompletedProcess(command, 1, stdout=b"", stderr=b"decode failed")

    monkeypatch.setattr(native_audio.subprocess, "run", fake_run)

    with pytest.raises(ValueError, match="ffmpeg failed with exit code 1: decode failed"):
        NativeAudioExtractor().extract_window("uploaded.mp4", start_seconds=0, duration_seconds=1)


def test_extract_window_fails_closed_on_empty_stdout(monkeypatch):
    def fake_run(command, **_kwargs):
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(native_audio.subprocess, "run", fake_run)

    with pytest.raises(ValueError, match="native audio output is empty"):
        NativeAudioExtractor().extract_window("uploaded.mp4", start_seconds=0, duration_seconds=1)


def test_extract_window_fails_closed_when_duration_exceeds_limit(monkeypatch):
    def fake_run(*_args, **_kwargs):
        raise AssertionError("ffmpeg must not run for overlong windows")

    monkeypatch.setattr(native_audio.subprocess, "run", fake_run)

    with pytest.raises(ValueError, match="duration exceeds 30s"):
        NativeAudioExtractor().extract_window("uploaded.mp4", start_seconds=0, duration_seconds=30.001)


def test_native_audio_module_has_no_analysis_transcript_or_vad_logic():
    assert native_audio.__file__ is not None
    source = Path(native_audio.__file__).read_text()

    forbidden_terms = [
        "audio_analysis",
        "transcript",
        "asr",
        "vad",
        "vocal_cue",
        "silence_detected",
    ]
    assert [term for term in forbidden_terms if term in source.lower()] == []
