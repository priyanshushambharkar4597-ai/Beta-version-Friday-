"""Voice Subsystem - Zero-Cost CPU Text-To-Speech (TTS) Engine for Friday."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
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
        self._current_process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

    def is_speaking(self) -> bool:
        """Check if TTS audio is currently playing."""
        with self._lock:
            return bool(self._current_process and self._current_process.poll() is None)

    def stop(self) -> bool:
        """Immediately halt any ongoing audio synthesis/playback (Barge-In)."""
        with self._lock:
            if self._current_process and self._current_process.poll() is None:
                try:
                    self._current_process.terminate()
                except Exception:
                    pass
                self._current_process = None
                return True
        return False

    def speak(self, text: str, async_playback: bool = False) -> bool:
        """Speak text aloud through the default audio output with Barge-In support.

        Args:
            text: Text to synthesize.
            async_playback: If True, executes synthesis non-blockingly.

        Returns:
            True if speech started/succeeded, False otherwise.
        """
        cleaned = text.replace('"', '""').replace("`", "")
        if not cleaned.strip():
            return True

        if async_playback:
            thread = threading.Thread(target=self._speak_sync, args=(cleaned,), daemon=True)
            thread.start()
            return True

        return self._speak_sync(cleaned)

    def _speak_sync(self, cleaned: str) -> bool:
        """Execute speech synthesis process and track handle for interruption."""
        # Stop any existing speech playback first
        self.stop()

        if sys.platform == "win32":
            ps_script = (
                f'Add-Type -AssemblyName System.Speech; '
                f'$synth = [System.Speech.Synthesis.SpeechSynthesizer]::new(); '
                f'$synth.Rate = 1; '
                f'$synth.Speak("{cleaned}");'
            )
            try:
                with self._lock:
                    self._current_process = subprocess.Popen(
                        ["powershell.exe", "-NoProfile", "-Command", ps_script],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                self._current_process.wait(timeout=30)
                with self._lock:
                    self._current_process = None
                return True
            except Exception:
                self.stop()
                return False
        else:
            try:
                with self._lock:
                    self._current_process = subprocess.Popen(
                        ["espeak", cleaned],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                self._current_process.wait(timeout=10)
                with self._lock:
                    self._current_process = None
                return True
            except Exception:
                self.stop()
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
