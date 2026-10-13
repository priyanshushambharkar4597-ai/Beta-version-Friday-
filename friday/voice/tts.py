"""Voice Subsystem - Neural Edge-TTS Engine with SAPI5 Fallback for Friday."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Optional

try:
    import edge_tts
    _HAS_EDGE_TTS = True
except ImportError:
    _HAS_EDGE_TTS = False

DEFAULT_PRIMARY_VOICE = "en-IE-EmilyNeural"
DEFAULT_FALLBACK_VOICE = "en-GB-SoniaNeural"


class FridayTTS:
    """CPU-only Text-To-Speech synthesizer.

    Features:
    - Primary: High-fidelity Microsoft Edge neural TTS (en-IE-EmilyNeural).
    - Secondary Fallback: en-GB-SoniaNeural.
    - Offline Zero-Crash Fallback: Windows System.Speech SAPI5.
    - Full Barge-In support via interruptible process tracking.
    """

    def __init__(
        self,
        primary_voice: str = DEFAULT_PRIMARY_VOICE,
        fallback_voice: str = DEFAULT_FALLBACK_VOICE,
        use_edge_tts: bool = True,
        piper_binary: Optional[str] = None,
    ) -> None:
        """Initialize TTS engine.

        Args:
            primary_voice: Edge TTS voice identifier.
            fallback_voice: Secondary Edge TTS voice identifier.
            use_edge_tts: Whether to attempt neural edge-tts before SAPI5.
            piper_binary: Optional legacy piper path.
        """
        self.primary_voice = primary_voice
        self.fallback_voice = fallback_voice
        self.use_edge_tts = use_edge_tts and _HAS_EDGE_TTS
        self.piper_binary = piper_binary
        self._current_process: Optional[subprocess.Popen] = None
        self._active_tmp_file: Optional[str] = None
        self._lock = threading.Lock()

    def is_speaking(self) -> bool:
        """Check if TTS audio is currently playing."""
        with self._lock:
            return bool(self._current_process and self._current_process.poll() is None)

    def stop(self) -> bool:
        """Immediately halt any ongoing audio synthesis/playback (Barge-In)."""
        with self._lock:
            terminated = False
            if self._current_process and self._current_process.poll() is None:
                try:
                    self._current_process.terminate()
                    terminated = True
                except Exception:
                    pass
                self._current_process = None

            if self._active_tmp_file:
                if os.path.exists(self._active_tmp_file):
                    try:
                        os.remove(self._active_tmp_file)
                    except Exception:
                        pass
                self._active_tmp_file = None

            return terminated

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
        self.stop()

        # 1. Attempt Edge-TTS neural speech if enabled
        if self.use_edge_tts and sys.platform == "win32":
            success = self._speak_edge_tts(cleaned)
            if success:
                return True

        # 2. Seamless zero-crash fallback to Windows SAPI5
        return self._speak_sapi5(cleaned)

    def _speak_edge_tts(self, text: str) -> bool:
        """Synthesize via Edge-TTS and play through Windows Media Player with Barge-In tracking."""
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(prefix="friday_voice_", suffix=".mp3")
            os.close(fd)
            with self._lock:
                self._active_tmp_file = tmp_path

            # Try primary voice first, then fallback voice
            synthesized = False
            for voice in (self.primary_voice, self.fallback_voice):
                try:
                    asyncio.run(self._save_edge_tts(text, voice, tmp_path))
                    synthesized = True
                    break
                except Exception:
                    continue

            if not synthesized or not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
                return False

            # Playback script using presentationCore MediaPlayer
            normalized_path = tmp_path.replace("\\", "/")
            ps_script = (
                'Add-Type -AssemblyName presentationCore; '
                f'$p = New-Object System.Windows.Media.MediaPlayer; '
                f'$p.Open([System.Uri]"{normalized_path}"); '
                '$p.Play(); '
                '$w = 0; while (-not $p.NaturalDuration.HasTimeSpan -and $w -lt 4000) { Start-Sleep -Milliseconds 50; $w += 50 }; '
                'if ($p.NaturalDuration.HasTimeSpan) { Start-Sleep -Milliseconds ([int]$p.NaturalDuration.TimeSpan.TotalMilliseconds + 150) }; '
                '$p.Close()'
            )

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
            return False
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
                with self._lock:
                    if self._active_tmp_file == tmp_path:
                        self._active_tmp_file = None

    async def _save_edge_tts(self, text: str, voice: str, out_path: str) -> None:
        """Asynchronously stream and write Edge-TTS output."""
        communicate = edge_tts.Communicate(text=text, voice=voice)
        await communicate.save(out_path)

    def _speak_sapi5(self, cleaned: str) -> bool:
        """Fallback to Windows native SAPI5 speech synthesis."""
        if sys.platform == "win32":
            ps_script = (
                'Add-Type -AssemblyName System.Speech; '
                '$synth = [System.Speech.Synthesis.SpeechSynthesizer]::new(); '
                '$synth.Rate = 1; '
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
        """Synthesize text and write to an audio file (MP3 or WAV).

        Args:
            text: Text to synthesize.
            out_path: Output file path.

        Returns:
            True if file was created, False otherwise.
        """
        cleaned = text.replace('"', '""').replace("`", "")
        resolved_out = Path(out_path).resolve()
        resolved_out.parent.mkdir(parents=True, exist_ok=True)

        # If edge_tts is enabled, attempt neural generation directly
        if self.use_edge_tts:
            try:
                asyncio.run(self._save_edge_tts(cleaned, self.primary_voice, str(resolved_out)))
                if resolved_out.exists() and resolved_out.stat().st_size > 0:
                    return True
            except Exception:
                pass

        # SAPI5 fallback file generation (WAV)
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
                return proc.returncode == 0 and resolved_out.exists() and resolved_out.stat().st_size > 0
            except Exception:
                return False
        return False
