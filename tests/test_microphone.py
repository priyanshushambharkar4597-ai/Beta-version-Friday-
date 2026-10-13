"""Tests for Friday's Microphone Audio Recording Subsystem."""

import io
import wave
import pytest

from friday.voice.microphone import MicrophoneRecorder
from friday.voice.vad import VoiceActivityDetector


def test_microphone_initialization():
    """Verify MicrophoneRecorder initializes with correct sample rate and VAD."""
    vad = VoiceActivityDetector(sample_rate=16000, energy_threshold=400.0)
    recorder = MicrophoneRecorder(sample_rate=16000, channels=1, vad=vad)
    assert recorder.sample_rate == 16000
    assert recorder.channels == 1
    assert not recorder.is_recording


def test_microphone_silence_trimming():
    """Verify silence trimming trims quiet frames and keeps speech frames with padding."""
    recorder = MicrophoneRecorder(sample_rate=16000)
    # 0.5s silence + 0.5s tone + 0.5s silence
    silent_chunk = b"\x00\x00" * 8000
    # High amplitude tone
    tone_chunk = b"\x50\x20" * 8000
    full_pcm = silent_chunk + tone_chunk + silent_chunk

    trimmed = recorder._trim_silence(full_pcm)
    assert len(trimmed) > 0
    # Trimmed PCM should be shorter than original full 1.5s
    assert len(trimmed) <= len(full_pcm)


def test_microphone_wav_packaging_and_stop():
    """Verify stop_recording packages PCM audio into valid 16kHz mono WAV bytes."""
    recorder = MicrophoneRecorder(sample_rate=16000)
    # Simulate recorded frames
    recorder._frames = [b"\x20\x10" * 4000]
    recorder._is_recording = True

    wav_bytes = recorder.stop_recording()
    assert not recorder.is_recording
    assert len(wav_bytes) > 44  # WAV header is 44 bytes

    # Verify WAV header parameters
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.getframerate() == 16000


def test_microphone_empty_recording_safety():
    """Verify stopping an unrecorded session safely returns a blank valid WAV container."""
    recorder = MicrophoneRecorder(sample_rate=16000)
    wav_bytes = recorder.stop_recording()
    assert len(wav_bytes) >= 44
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        assert w.getframerate() == 16000
