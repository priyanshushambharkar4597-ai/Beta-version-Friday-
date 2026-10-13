"""Voice Subsystem - Non-blocking Microphone Audio Recorder with VAD Silence Trimming."""

from __future__ import annotations

import io
import logging
import threading
from typing import List, Optional

import numpy as np

from friday.voice.vad import VoiceActivityDetector

logger = logging.getLogger("friday.voice.microphone")


class MicrophoneRecorder:
    """Non-blocking 16kHz mono audio recorder with in-RAM WAV packaging and VAD trimming."""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        vad: Optional[VoiceActivityDetector] = None,
    ) -> None:
        """Initialize microphone recorder.

        Args:
            sample_rate: Audio sampling frequency in Hz (default: 16000 standard).
            channels: Number of channels (default: 1 for mono).
            vad: Voice Activity Detector for silence trimming.
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.vad = vad or VoiceActivityDetector(sample_rate=sample_rate)

        self._stream = None
        self._frames: List[bytes] = []
        self._is_recording = False
        self._lock = threading.Lock()

    @property
    def is_recording(self) -> bool:
        """Return whether microphone is actively recording."""
        with self._lock:
            return self._is_recording

    def start_recording(self) -> bool:
        """Start capturing audio frames in a non-blocking background stream.

        Returns:
            True if recording started successfully, False otherwise.
        """
        with self._lock:
            if self._is_recording:
                return True
            self._frames = []
            self._is_recording = True

        try:
            import sounddevice as sd

            def audio_callback(indata, frames, time_info, status):
                if status:
                    logger.debug(f"Sounddevice status: {status}")
                with self._lock:
                    if self._is_recording:
                        # indata is numpy array (frames, channels) int16
                        self._frames.append(indata.tobytes())

            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
                callback=audio_callback,
            )
            self._stream.start()
            logger.info("Microphone recording started.")
            return True
        except Exception as exc:
            logger.warning(f"Could not open sounddevice audio stream: {exc}")
            with self._lock:
                self._is_recording = False
            return False

    def stop_recording(self) -> bytes:
        """Stop recording, trim leading/trailing silence, and return WAV bytes in RAM.

        Returns:
            Standard 16kHz mono 16-bit WAV bytes.
        """
        with self._lock:
            if not self._is_recording and not self._frames:
                # Return 0.2s of blank WAV if nothing recorded
                return self.vad.create_wav_bytes(b"\x00\x00" * int(self.sample_rate * 0.2))
            self._is_recording = False

        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as exc:
                logger.debug(f"Error closing stream: {exc}")
            self._stream = None

        with self._lock:
            raw_pcm = b"".join(self._frames)
            self._frames = []

        if not raw_pcm:
            return self.vad.create_wav_bytes(b"\x00\x00" * int(self.sample_rate * 0.2))

        # Trim silence using VoiceActivityDetector
        trimmed_pcm = self._trim_silence(raw_pcm)
        return self.vad.create_wav_bytes(trimmed_pcm)

    def _trim_silence(self, pcm_bytes: bytes) -> bytes:
        """Trim leading and trailing silence based on energy segments with 100ms padding."""
        segments = self.vad.segment_speech(pcm_bytes)
        if not segments:
            # If no speech detected above threshold, return original PCM
            return pcm_bytes

        # Start from first segment start, end at last segment end
        start_idx = segments[0][0]
        end_idx = segments[-1][1]

        # Add 100ms (1600 samples * 2 bytes = 3200 bytes) padding
        padding_bytes = int(self.sample_rate * 0.1) * 2
        safe_start = max(0, start_idx - padding_bytes)
        safe_end = min(len(pcm_bytes), end_idx + padding_bytes)

        trimmed = pcm_bytes[safe_start:safe_end]
        return trimmed if len(trimmed) > 0 else pcm_bytes

    def record_fixed_duration(self, seconds: float = 2.0) -> bytes:
        """Record audio for a fixed duration synchronously (useful for testing)."""
        import time

        self.start_recording()
        time.sleep(seconds)
        return self.stop_recording()
