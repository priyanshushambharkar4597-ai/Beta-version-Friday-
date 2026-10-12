"""Voice Subsystem - CPU-based Voice Activity Detection & Audio Processing."""

from __future__ import annotations

import io
import math
import struct
import wave
from pathlib import Path
from typing import Any, List, Optional, Tuple


class VoiceActivityDetector:
    """CPU-only Voice Activity Detection (VAD) and audio framing engine."""

    def __init__(
        self,
        energy_threshold: float = 500.0,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
    ) -> None:
        """Initialize VAD.

        Args:
            energy_threshold: RMS amplitude threshold above which speech is detected.
            sample_rate: Audio sampling rate (default 16kHz standard for VAD/Gemini).
            frame_duration_ms: Frame size in milliseconds.
        """
        self.energy_threshold = energy_threshold
        self.sample_rate = sample_rate
        self.frame_size = int(sample_rate * (frame_duration_ms / 1000.0))

    def compute_frame_rms(self, frame_bytes: bytes) -> float:
        """Calculate Root Mean Square (RMS) energy of a 16-bit PCM frame."""
        num_samples = len(frame_bytes) // 2
        if num_samples == 0:
            return 0.0

        samples = struct.unpack(f"<{num_samples}h", frame_bytes[: num_samples * 2])
        sum_squares = sum(float(s) * float(s) for s in samples)
        return math.sqrt(sum_squares / num_samples)

    def is_speech(self, frame_bytes: bytes) -> bool:
        """Check if an audio frame contains voice activity."""
        rms = self.compute_frame_rms(frame_bytes)
        return rms >= self.energy_threshold

    def segment_speech(
        self, audio_bytes: bytes
    ) -> List[Tuple[int, int]]:
        """Identify start and end sample indices of speech segments.

        Args:
            audio_bytes: Raw 16-bit mono PCM bytes at 16kHz.

        Returns:
            List of (start_byte_idx, end_byte_idx) containing speech.
        """
        bytes_per_frame = self.frame_size * 2
        segments: List[Tuple[int, int]] = []
        in_speech = False
        speech_start = 0

        for i in range(0, len(audio_bytes), bytes_per_frame):
            frame = audio_bytes[i : i + bytes_per_frame]
            if len(frame) < bytes_per_frame:
                break

            active = self.is_speech(frame)
            if active and not in_speech:
                in_speech = True
                speech_start = i
            elif not active and in_speech:
                in_speech = False
                segments.append((speech_start, i))

        if in_speech:
            segments.append((speech_start, len(audio_bytes)))

        return segments

    def create_wav_bytes(self, pcm_bytes: bytes) -> bytes:
        """Package raw 16-bit PCM samples into standard WAV container."""
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self.sample_rate)
            wav.writeframes(pcm_bytes)
        return buffer.getvalue()
