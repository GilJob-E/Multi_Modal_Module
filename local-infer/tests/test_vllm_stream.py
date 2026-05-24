from local_infer.vllm_stream import iter_sse_delta_text


def sse(obj: str) -> bytes:
    return ("data: " + obj).encode("utf-8")


def test_iter_sse_delta_text_extracts_content_chunks_and_ignores_done():
    lines = [
        b"",
        sse('{"choices":[{"delta":{"role":"assistant"}}]}'),
        sse('{"choices":[{"delta":{"content":"안"}}]}'),
        sse('{"choices":[{"delta":{"content":"녕"}}]}'),
        b"data: [DONE]",
    ]

    assert list(iter_sse_delta_text(lines)) == ["안", "녕"]


def test_iter_sse_delta_text_skips_malformed_lines_without_stopping_stream():
    lines = [
        b"event: ping",
        b"data: not-json",
        sse('{"choices":[{"delta":{"content":"계속"}}]}'),
    ]

    assert list(iter_sse_delta_text(lines)) == ["계속"]
