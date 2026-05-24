# pyright: reportMissingImports=false
from pathlib import Path

import local_infer.app as native_app
import local_infer.native_audio as native_audio
import local_infer.native_media_store as native_media_store
import local_infer.native_payloads as native_payloads


FORBIDDEN_NATIVE_MODULE_TERMS = [
    "audio_analysis",
    "generate_av_fallback",
    "build_chat_payload",
    "FrameStore",
    "transcript",
    "asr",
    "vad",
]

FORBIDDEN_NATIVE_APP_BLOCK_TERMS = [
    "analyze_wav_bytes",
    "audio_store",
    "get_recent_frames",
    "build_chat_payload",
    "generate_av_fallback",
    "/generate-av-fallback",
    "image_url",
]


def _source(module) -> str:
    assert module.__file__ is not None
    return Path(module.__file__).read_text()


def _compact(text: str) -> str:
    return "".join(text.split())


def test_native_modules_do_not_import_or_emit_fallback_frame_or_analysis_paths():
    modules = {
        "native_payloads": _source(native_payloads),
        "native_audio": _source(native_audio),
        "native_media_store": _source(native_media_store),
    }

    for name, source in modules.items():
        lowered = source.lower()
        forbidden = [term for term in FORBIDDEN_NATIVE_MODULE_TERMS if term.lower() in lowered]
        assert forbidden == [], f"{name} contains forbidden native-path terms: {forbidden}"

        compact = _compact(source)
        assert '"type":"image_url"' not in compact, f"{name} emits image_url content parts"
        assert "'type':'image_url'" not in compact, f"{name} emits image_url content parts"


def test_app_native_endpoint_block_is_bounded_and_separate_from_fallback_paths():
    source = _source(native_app)
    begin = "# Native streaming endpoints begin"
    end = "# Native streaming endpoints end"

    assert begin in source
    assert end in source

    native_block = source.split(begin, 1)[1].split(end, 1)[0]
    forbidden = [term for term in FORBIDDEN_NATIVE_APP_BLOCK_TERMS if term in native_block]
    assert forbidden == [], f"native endpoint block contains fallback/frame terms: {forbidden}"


def test_app_native_endpoint_block_exposes_only_locked_native_routes():
    source = _source(native_app)
    native_block = source.split("# Native streaming endpoints begin", 1)[1].split(
        "# Native streaming endpoints end", 1
    )[0]

    assert "/v1/native/sessions/{session_id}/windows" in native_block
    assert "/v1/native/sessions/{session_id}/generate" in native_block
    assert "/v1/sessions/{session_id}/frames" not in native_block
    assert "/v1/sessions/{session_id}/audio" not in native_block
    assert "/v1/sessions/{session_id}/generate" not in native_block
