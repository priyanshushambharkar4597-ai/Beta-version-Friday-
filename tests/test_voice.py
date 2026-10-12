"""Unit tests for Friday Voice subsystem (TTS and VAD)."""

import struct
from pathlib import Path
import pytest

from friday.voice.tts import FridayTTS
from friday.voice.vad import VoiceActivityDetector


def test_voice_activity_detector():
    vad = VoiceActivityDetector(energy_threshold=500.0, sample_rate=16000)

    # 1. Silent frame (all zeros)
    silent_pcm = b"\x00" * (vad.frame_size * 2)
    assert vad.compute_frame_rms(silent_pcm) == 0.0
    assert vad.is_speech(silent_pcm) is False

    # 2. Loud frame (amplitude 3000)
    loud_samples = [3000] * vad.frame_size
    loud_pcm = struct.pack(f"<{vad.frame_size}h", *loud_samples)
    rms = vad.compute_frame_rms(loud_pcm)
    assert rms == pytest.approx(3000.0, rel=1e-2)
    assert vad.is_speech(loud_pcm) is True

    # 3. Speech segmentation
    mixed_pcm = silent_pcm + loud_pcm + silent_pcm
    segments = vad.segment_speech(mixed_pcm)
    assert len(segments) == 1

    # 4. WAV container packaging
    wav_data = vad.create_wav_bytes(loud_pcm)
    assert wav_data[:4] == b"RIFF"
    assert wav_data[8:12] == b"WAVE"


def test_friday_tts_synthesis(tmp_path: Path):
    tts = FridayTTS()

    # Empty text handled cleanly
    assert tts.speak("") is True

    # Synthesize to wav file on disk
    out_file = tmp_path / "test_synth.wav"
    res = tts.synthesize_to_file("Friday audio test.", str(out_file))
    assert res is True
    assert out_file.exists()
    assert out_file.stat().st_size > 0
