# pyright: reportMissingImports=false
from pathlib import Path

from local_infer.audio_analysis import analyze_wav_bytes


FIXTURES = Path(__file__).resolve().parents[2] / ".sisyphus" / "evidence" / "audio-fixtures"


def test_audio_analysis_classifies_silence_fixture():
    analysis = analyze_wav_bytes((FIXTURES / "no_audio_ablation.wav").read_bytes())

    assert analysis.label == "silence/no-audio"
    assert analysis.silence_detected is True
    assert analysis.vocal_cue_detected is False


def test_audio_analysis_classifies_beep_fixture():
    analysis = analyze_wav_bytes((FIXTURES / "beep_only.wav").read_bytes())

    assert analysis.label == "beep/tone"
    assert analysis.beep_tone_detected is True
    assert analysis.vocal_cue_detected is False
    assert analysis.dominant_frequency_hz is not None
    assert analysis.dominant_frequency_hz > 650


def test_audio_analysis_classifies_cross_modal_vocal_cue_fixture():
    analysis = analyze_wav_bytes((FIXTURES / "cross_modal_event.wav").read_bytes())

    assert analysis.label == "vocal-cue/sustained-ah"
    assert analysis.vocal_cue_detected is True
    assert analysis.longest_active_ms >= 500
    assert analysis.dominant_frequency_hz is not None
    assert 150 <= analysis.dominant_frequency_hz <= 650
