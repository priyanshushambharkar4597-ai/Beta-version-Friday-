"""Unit tests for Neural Edge-TTS Engine and SAPI5 Fallback."""

import subprocess
from unittest.mock import MagicMock, patch
import pytest

from friday.voice.tts import FridayTTS, DEFAULT_PRIMARY_VOICE, DEFAULT_FALLBACK_VOICE


def test_friday_tts_voice_configuration():
    """Verify default Irish persona voice en-IE-EmilyNeural and fallback voice."""
    tts = FridayTTS()
    assert tts.primary_voice == "en-IE-EmilyNeural"
    assert tts.fallback_voice == "en-GB-SoniaNeural"
    assert tts.use_edge_tts is True


def test_friday_tts_fallback_to_sapi5_when_edge_disabled():
    """Verify seamless fallback to Windows SAPI5 when Edge-TTS is disabled or offline."""
    tts = FridayTTS(use_edge_tts=False)

    with patch.object(tts, "_speak_sapi5", return_value=True) as mock_sapi:
        success = tts.speak("Testing fallback mechanism.")
        assert success is True
        mock_sapi.assert_called_once()


def test_friday_tts_edge_tts_failure_falls_back_to_sapi5():
    """Verify that if Edge-TTS synthesis raises an exception, SAPI5 is seamlessly invoked."""
    tts = FridayTTS(use_edge_tts=True)

    with patch.object(tts, "_speak_edge_tts", return_value=False) as mock_edge, \
         patch.object(tts, "_speak_sapi5", return_value=True) as mock_sapi:

        success = tts.speak("Testing zero-crash fallback.")
        assert success is True
        mock_edge.assert_called_once()
        mock_sapi.assert_called_once()


def test_friday_tts_barge_in_and_temp_cleanup():
    """Verify barge-in stop terminates process and removes active temporary file."""
    tts = FridayTTS()
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    tts._current_process = mock_proc
    tts._active_tmp_file = "non_existent_temp.mp3"

    assert tts.is_speaking() is True
    stopped = tts.stop()
    assert stopped is True
    mock_proc.terminate.assert_called_once()
    assert tts._current_process is None
    assert tts._active_tmp_file is None
