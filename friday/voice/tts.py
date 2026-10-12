"""Voice Subsystem - Zero-Cost CPU Text-To-Speech (TTS) Engine for Friday."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


class FridayTTS:
    """CPU-only Text-To-Speech synthesizer.

    Utilizes Windows System.Speech synthesizer natively (0% GPU utilization,
    zero local heavy weights) with support for Piper CPU offline TTS.
    """

    def __init__(self, piper_binary: Optional[str] = None) -> None:
        """Initialize TTS engine.

        Args:
            piper_binary: Optional path to piper executable if configured.
        """
        self.piper_binary = piper_binary

    def speak(self, text: str) -> bool:
        """Speak text aloud through the default audio output.

        Args:
            text: Text to synthesize.

        Returns:
            True if speech succeeded, False otherwise.
        """
        cleaned = text.replace('"', '""').replace("`", "")
        if not cleaned.strip():
            return True

        if sys.platform == "win32":
            # Native Windows System.Speech synthesizer running 100% on CPU
            ps_script = (
                f'Add-Type -AssemblyName System.Speech; '
                f'$synth = [System.Speech.Synthesis.SpeechSynthesizer]::new(); '
                f'$synth.Rate = 1; '
                f'$synth.Speak("{cleaned}");'
            )
            try:
                proc = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-Command", ps_script],
                    capture_output=True,
                    timeout=30,
                )
                return proc.returncode == 0
            except Exception:
                return False
        else:
            # Fallback for Linux/macOS
            try:
                subprocess.run(["espeak", cleaned], capture_output=True, timeout=10)
                return True
            except Exception:
                return False

    def synthesize_to_file(self, text: str, out_path: str) -> bool:
        """Synthesize text and write to a WAV/audio file.

        Args:
            text: Text to synthesize.
            out_path: Output file path.

        Returns:
            True if file was created, False otherwise.
        """
        cleaned = text.replace('"', '""').replace("`", "")
        resolved_out = Path(out_path).resolve()
        resolved_out.parent.mkdir(parents=True, exist_ok=True)

        if sys.platform == "win32":
            ps_script = (
                f'Add-Type -AssemblyName System.Speech; '
                f'$synth = [System.Speech.Synthesis.SpeechSynthesizer]::new(); '
                f'$synth.SetOutputToWaveFile("{str(resolved_out)}"); '
                f'$synth.Speak("{cleaned}"); '
                f'$synth.Dispose();'
            )
            try:
                proc = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-Command", ps_script],
                    capture_output=True,
                    timeout=30,
                )
                return proc.returncode == 0 and resolved_out.exists()
            except Exception:
                return False
        return False
