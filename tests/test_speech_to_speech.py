"""Tests for Friday's Low-Latency Speech-to-Speech Voice Pipeline & Barge-In."""

import io
import wave
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from friday.agent import FridayAgent
from friday.llm.gemini_provider import GeminiProvider
from friday.server import app
from friday.tools.base import PermissionGate
from friday.voice.tts import FridayTTS


def _create_mock_wav_bytes(duration_sec: float = 0.5) -> bytes:
    """Helper to generate mock 16kHz mono WAV bytes in memory."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        num_samples = int(duration_sec * 16000)
        w.writeframes(b"\x20\x00" * num_samples)
    return buf.getvalue()


def test_tts_barge_in_stop():
    """Verify FridayTTS stop() terminates current process handle safely."""
    tts = FridayTTS()
    # If not speaking, stop returns False without crashing
    assert not tts.is_speaking()
    assert not tts.stop()

    # Simulate an active subprocess handle
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    tts._current_process = mock_proc

    assert tts.is_speaking()
    assert tts.stop()
    mock_proc.terminate.assert_called_once()
    assert not tts.is_speaking()


def test_gemini_generate_with_audio():
    """Verify GeminiProvider formats audio blob and invokes model with audio."""
    provider = GeminiProvider(api_key="mock_key")
    provider._model = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "I heard your spoken instruction."
    provider._model.generate_content.return_value = mock_resp

    wav_bytes = _create_mock_wav_bytes(0.2)
    reply = provider.generate_with_audio("Listen to this", wav_bytes)

    assert "heard" in reply.lower()
    provider._model.generate_content.assert_called_once()


def test_agent_handle_audio_spoken_remember_acceptance(tmp_path):
    """Acceptance test: spoken audio command triggers tool execution and Obsidian vault note."""
    provider = GeminiProvider(api_key="mock_key")
    gate = PermissionGate()
    agent = FridayAgent(gemini_provider=provider, permission_gate=gate)

    # Point vault to temporary directory for clean isolation
    agent.memory.vault.vault_dir = tmp_path
    agent.memory.vault.vault_dir.mkdir(parents=True, exist_ok=True)

    # Mock Gemini audio response with an action block to save the RC filter cutoff note
    action_reply = (
        "I will record the RC filter parameter for you.\n"
        "```action\n"
        "{\n"
        '  "tool": "remember",\n'
        '  "parameters": {\n'
        '    "title": "RC Filter Cutoff",\n'
        '    "content": "Cutoff frequency for the RC filter is 1.5 kHz",\n'
        '    "category": "entc_coursework"\n'
        "  }\n"
        "}\n"
        "```"
    )

    with patch.object(provider, "generate_with_audio", return_value=action_reply), \
         patch.object(provider, "chat", return_value="Noted, Boss. Cutoff frequency of 1.5 kHz saved to your vault."):

        wav_bytes = _create_mock_wav_bytes(1.0)
        final_reply = agent.handle_audio(wav_bytes)

        # 1. Spoken confirmation returned
        assert "saved to your vault" in final_reply

        # 2. Verify Obsidian note physically written to vault
        notes = agent.memory.list_all_titles()
        assert "RC Filter Cutoff" in notes

        note_file = tmp_path / "RC-Filter-Cutoff.md"
        assert note_file.exists()
        content = note_file.read_text(encoding="utf-8")
        assert "1.5 kHz" in content


def test_api_voice_endpoint():
    """Verify FastAPI /api/voice endpoint accepts audio bytes and returns reply."""
    client = TestClient(app)
    wav_bytes = _create_mock_wav_bytes(0.5)

    with patch("friday.server.get_agent") as mock_get_agent:
        mock_agent = MagicMock()
        mock_agent.llm.model_name = "gemini-3.6-flash"
        mock_agent.llm.is_configured.return_value = True
        mock_agent.handle_audio.return_value = "Audio received loud and clear, Boss."
        mock_get_agent.return_value = mock_agent

        response = client.post(
            "/api/voice",
            content=wav_bytes,
            headers={"Content-Type": "audio/wav"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "loud and clear" in data["response"]
        assert data["brain_online"] is True
