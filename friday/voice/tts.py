"""Voice Subsystem - Neural Edge-TTS Engine with SAPI5 Fallback & Streaming Playback for Friday."""

from __future__ import annotations

import asyncio
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable, Generator, Iterable, Optional

try:
    import edge_tts
    _HAS_EDGE_TTS = True
except ImportError:
    _HAS_EDGE_TTS = False

DEFAULT_PRIMARY_VOICE = "en-IE-EmilyNeural"
DEFAULT_FALLBACK_VOICE = "en-GB-SoniaNeural"


def clean_for_speech(text: str) -> str:
    """Scrub markdown, equations, code blocks, and URLs for natural vocalization."""
    if not text:
        return ""
    # Strip action blocks and general code fences
    text = re.sub(r"```action[\s\S]*?```", "", text)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]*`", "", text)
    # Strip markdown links [label](url) -> label
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    # Strip wikilinks [[label]] -> label
    text = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", r"\1", text)
    # Strip markdown bold/italic/headers
    text = re.sub(r"[#*_~>]+", "", text)
    # Strip bullet indicators
    text = re.sub(r"^\s*[-*•]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    # Strip LaTeX math blocks
    text = re.sub(r"\$\$[\s\S]*?\$\$", "", text)
    text = re.sub(r"\$[^\$]*\$", "", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


class FridayTTS:
    """CPU-only Text-To-Speech synthesizer.

    Features:
    - Primary: High-fidelity Microsoft Edge neural TTS (en-IE-EmilyNeural).
    - Secondary Fallback: en-GB-SoniaNeural.
    - Offline Zero-Crash Fallback: Windows System.Speech SAPI5.
    - Sub-second In-Process MCI Playback on Windows (< 5ms dispatch).
    - Sentence-Level Streaming TTS with continuous pipeline.
    - Full Barge-In support via interruptible MCI handle and process tracking.
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
        self._active_mci_alias: Optional[str] = None
        self._cancel_stream: bool = False
        self._lock = threading.Lock()

    def is_speaking(self) -> bool:
        """Check if TTS audio is currently playing."""
        with self._lock:
            proc_speaking = bool(self._current_process and self._current_process.poll() is None)
            mci_speaking = bool(self._active_mci_alias is not None)
            return proc_speaking or mci_speaking

    def stop(self) -> bool:
        """Immediately halt any ongoing audio synthesis/playback (Barge-In)."""
        with self._lock:
            self._cancel_stream = True
            terminated = False

            # Halt Windows native MCI in-process playback
            if self._active_mci_alias and sys.platform == "win32":
                try:
                    import ctypes
                    winmm = ctypes.windll.winmm
                    winmm.mciSendStringW(f"stop {self._active_mci_alias}", None, 0, 0)
                    winmm.mciSendStringW(f"close {self._active_mci_alias}", None, 0, 0)
                    terminated = True
                except Exception:
                    pass
                self._active_mci_alias = None

            # Halt subprocess playback handle if present
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
        cleaned = clean_for_speech(text)
        if not cleaned:
            return True

        if async_playback:
            thread = threading.Thread(target=self._speak_sync, args=(cleaned,), daemon=True)
            thread.start()
            return True

        return self._speak_sync(cleaned)

    def speak_stream(
        self,
        sentence_stream: Iterable[str],
        on_sentence_start: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Stream sentences sequentially with concurrent ahead-of-time synthesis.

        As each sentence completes generation from LLM, it is synthesized concurrently
        and played seamlessly through the audio pipeline without waiting for the full response.
        """
        self.stop()
        with self._lock:
            self._cancel_stream = False

        audio_queue: queue.Queue[Optional[tuple[str, str]]] = queue.Queue(maxsize=4)

        def _synthesizer_worker():
            for raw_sentence in sentence_stream:
                if self._cancel_stream:
                    break
                sentence = clean_for_speech(raw_sentence)
                if not sentence:
                    continue

                tmp_path = None
                try:
                    fd, tmp_path = tempfile.mkstemp(prefix="friday_stream_", suffix=".mp3")
                    os.close(fd)

                    synthesized = False
                    if self.use_edge_tts:
                        for voice in (self.primary_voice, self.fallback_voice):
                            try:
                                asyncio.run(self._save_edge_tts(sentence, voice, tmp_path))
                                synthesized = True
                                break
                            except Exception:
                                continue

                    if synthesized and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                        audio_queue.put((sentence, tmp_path))
                    else:
                        # Fallback: put sentence with None path to trigger SAPI5
                        audio_queue.put((sentence, None))
                except Exception:
                    pass

            audio_queue.put(None)  # Sentinel

        # Start background synthesizer thread
        synth_thread = threading.Thread(target=_synthesizer_worker, daemon=True)
        synth_thread.start()

        # Main consumer plays each audio segment sequentially
        while not self._cancel_stream:
            try:
                item = audio_queue.get(timeout=10.0)
            except queue.Empty:
                break

            if item is None:
                break

            sentence, audio_path = item
            if self._cancel_stream:
                if audio_path and os.path.exists(audio_path):
                    try:
                        os.remove(audio_path)
                    except Exception:
                        pass
                break

            if on_sentence_start:
                try:
                    on_sentence_start(sentence)
                except Exception:
                    pass

            if audio_path and os.path.exists(audio_path):
                played = self._play_audio_mci(audio_path)
                if not played:
                    self._play_audio_process(audio_path)
                try:
                    os.remove(audio_path)
                except Exception:
                    pass
            else:
                self._speak_sapi5(sentence)

    def _speak_sync(self, cleaned: str) -> bool:
        """Execute speech synthesis process and track handle for interruption."""
        self.stop()
        with self._lock:
            self._cancel_stream = False

        # 1. Attempt Edge-TTS neural speech if enabled
        if self.use_edge_tts and sys.platform == "win32":
            success = self._speak_edge_tts(cleaned)
            if success:
                return True

        # 2. Seamless zero-crash fallback to Windows SAPI5
        return self._speak_sapi5(cleaned)

    def _speak_edge_tts(self, text: str) -> bool:
        """Synthesize via Edge-TTS and play through low-latency MCI or MediaPlayer."""
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

            # Low-latency playback via Windows MCI
            if sys.platform == "win32":
                played = self._play_audio_mci(tmp_path)
                if played:
                    return True

            # Process fallback if MCI unsupported on machine
            return self._play_audio_process(tmp_path)

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

    def _play_audio_mci(self, tmp_path: str) -> bool:
        """Play audio file via Windows MCI with instant barge-in support (< 5ms startup)."""
        if sys.platform != "win32":
            return False
        try:
            import ctypes
            winmm = ctypes.windll.winmm
            alias = f"friday_tts_{os.getpid()}_{threading.get_ident()}"
            winmm.mciSendStringW(f"close {alias}", None, 0, 0)

            normalized_path = os.path.abspath(tmp_path).replace("/", "\\")
            res = winmm.mciSendStringW(f'open "{normalized_path}" type mpegvideo alias {alias}', None, 0, 0)
            if res != 0:
                # Try waveaudio
                res = winmm.mciSendStringW(f'open "{normalized_path}" type waveaudio alias {alias}', None, 0, 0)
            if res != 0:
                return False

            with self._lock:
                self._active_mci_alias = alias

            # Play with wait (blocks thread until playback completes or stop() is called)
            winmm.mciSendStringW(f"play {alias} wait", None, 0, 0)
            winmm.mciSendStringW(f"close {alias}", None, 0, 0)

            with self._lock:
                if self._active_mci_alias == alias:
                    self._active_mci_alias = None
            return True
        except Exception:
            return False

    def _play_audio_process(self, tmp_path: str) -> bool:
        """Subprocess fallback playback using Windows MediaPlayer."""
        try:
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
        """Synthesize text and write to an audio file (MP3 or WAV)."""
        cleaned = clean_for_speech(text)
        resolved_out = Path(out_path).resolve()
        resolved_out.parent.mkdir(parents=True, exist_ok=True)

        if self.use_edge_tts:
            try:
                asyncio.run(self._save_edge_tts(cleaned, self.primary_voice, str(resolved_out)))
                if resolved_out.exists() and resolved_out.stat().st_size > 0:
                    return True
            except Exception:
                pass

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
