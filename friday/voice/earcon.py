"""Audio Earcon Synthesizer and Player for Friday.

Generates and plays low-latency, futuristic UI chimes (<5ms playback latency)
for instant tactile audio feedback on push-to-talk release and response completion.
"""

from __future__ import annotations

import math
import os
import struct
import sys
import wave
from pathlib import Path
from typing import Optional

ASSETS_DIR = Path(__file__).parent / "assets"


def _generate_wav(
    filename: Path,
    frequencies: list[tuple[float, float]],  # (freq_hz, duration_sec)
    sample_rate: int = 44100,
    amplitude: float = 0.35,
) -> None:
    """Generate a clean synthetic sine-wave audio chime with exponential decay envelope."""
    filename.parent.mkdir(parents=True, exist_ok=True)
    frames = bytearray()

    for freq, duration in frequencies:
        total_samples = int(sample_rate * duration)
        for i in range(total_samples):
            t = float(i) / sample_rate
            # Smooth exponential decay envelope
            envelope = math.exp(-3.5 * (t / duration))
            # Smooth attack for the first 5ms to avoid clicks
            if t < 0.005:
                envelope *= t / 0.005

            val = math.sin(2.0 * math.pi * freq * t) * envelope * amplitude
            sample = int(val * 32767.0)
            sample = max(-32768, min(32767, sample))
            frames.extend(struct.pack("<h", sample))

    with wave.open(str(filename), "wb") as wf:
        wf.setnchannels(1)  # Mono
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(frames)


def ensure_earcon_assets() -> tuple[Path, Path]:
    """Ensure audio_in.wav and audio_out.wav exist on disk, creating them if necessary."""
    in_wav = ASSETS_DIR / "audio_in.wav"
    out_wav = ASSETS_DIR / "audio_out.wav"

    if not in_wav.exists() or in_wav.stat().st_size == 0:
        # High-tech rising acknowledgment chime (E5 659Hz -> A5 880Hz)
        _generate_wav(in_wav, [(659.25, 0.06), (880.0, 0.09)], amplitude=0.4)

    if not out_wav.exists() or out_wav.stat().st_size == 0:
        # Soft descending ready chime (A5 880Hz -> C#5 554Hz)
        _generate_wav(out_wav, [(880.0, 0.05), (554.37, 0.08)], amplitude=0.35)

    return in_wav, out_wav


def play_audio_in() -> bool:
    """Play immediate acknowledgment earcon asynchronously (< 5ms dispatch)."""
    try:
        in_wav, _ = ensure_earcon_assets()
        if sys.platform == "win32":
            import winsound
            winsound.PlaySound(str(in_wav), winsound.SND_FILENAME | winsound.SND_ASYNC)
            return True
    except Exception:
        pass
    return False


def play_audio_out() -> bool:
    """Play completion earcon asynchronously."""
    try:
        _, out_wav = ensure_earcon_assets()
        if sys.platform == "win32":
            import winsound
            winsound.PlaySound(str(out_wav), winsound.SND_FILENAME | winsound.SND_ASYNC)
            return True
    except Exception:
        pass
    return False
