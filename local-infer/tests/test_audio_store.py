# pyright: reportMissingImports=false
import base64
import io
import wave

from local_infer.audio_store import AudioStore


def wav_b64(label: str) -> str:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(label.encode().ljust(320, b"\0"))
    return base64.b64encode(buffer.getvalue()).decode()


def test_audio_store_keeps_only_max_chunks_and_returns_recent_window():
    store = AudioStore(max_chunks_per_session=3)

    for index in range(5):
        store.add_chunk(
            "s1",
            timestamp_ms=index * 1000,
            audio_wav_base64=wav_b64(f"chunk-{index}"),
            duration_ms=400,
        )

    recent = store.get_recent_chunks("s1")
    window = store.get_window("s1", window_ms=1200)

    assert [chunk.timestamp_ms for chunk in recent] == [2000, 3000, 4000]
    assert [chunk.timestamp_ms for chunk in window] == [3000, 4000]
    assert store.total_duration_ms("s1") == 1200
