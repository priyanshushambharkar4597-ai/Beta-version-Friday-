"""Unit and integration tests for Friday Overhaul (Streaming TTS, Earcons, Brevity & HUD)."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from friday.agent import FridayAgent, stream_sentence_splitter
from friday.llm.gemini_provider import GeminiProvider
from friday.server import app
from friday.voice.earcon import ensure_earcon_assets, play_audio_in, play_audio_out
from friday.voice.tts import clean_for_speech


def test_clean_for_speech_scrubs_markdown_and_code():
    """Verify clean_for_speech removes code blocks, LaTeX, markdown symbols, and bullets."""
    raw = (
        "Here is the result:\n"
        "```python\n"
        "print('hello world')\n"
        "```\n"
        "The formula is $$H(s) = \\frac{1}{s+1}$$ and $f_c = 100$ Hz.\n"
        "- Bullet item 1\n"
        "- Bullet item 2\n"
        "**Bold text** and *italic text* with [link](http://example.com).\n"
        "```action\n"
        '{"tool": "remember"}\n'
        "```\n"
    )
    cleaned = clean_for_speech(raw)
    assert "```" not in cleaned
    assert "python" not in cleaned
    assert "print" not in cleaned
    assert "$$" not in cleaned
    assert "\\frac" not in cleaned
    assert "*" not in cleaned
    assert "-" not in cleaned
    assert "Bullet item" in cleaned
    assert "Bold text" in cleaned
    assert "http://example.com" not in cleaned


def test_stream_sentence_splitter():
    """Verify token chunks are cleanly separated into full sentences as boundaries arrive."""
    tokens = [
        "Transfer ", "function ", "analyzed. ",
        "Bode plot ", "and specs ", "are on ", "your HUD, sir! ",
        "Stability is verified."
    ]
    sentences = list(stream_sentence_splitter(tokens))
    assert len(sentences) == 3
    assert sentences[0] == "Transfer function analyzed."
    assert sentences[1] == "Bode plot and specs are on your HUD, sir!"
    assert sentences[2] == "Stability is verified."


def test_earcon_assets_generation():
    """Verify audio_in.wav and audio_out.wav are valid WAV files."""
    in_wav, out_wav = ensure_earcon_assets()
    assert in_wav.exists()
    assert out_wav.exists()
    assert in_wav.stat().st_size > 44  # WAV header is 44 bytes minimum
    assert out_wav.stat().st_size > 44

    # Test playback calls execute cleanly
    with patch("winsound.PlaySound") as mock_play:
        assert play_audio_in() is True
        mock_play.assert_called_once()

    with patch("winsound.PlaySound") as mock_play:
        assert play_audio_out() is True
        mock_play.assert_called_once()


def test_server_attachments_mount(tmp_path):
    """Verify static /attachments directory is mounted and accessible via HTTP."""
    client = TestClient(app)
    # Write a test file in vault/attachments
    att_dir = Path("vault/attachments")
    att_dir.mkdir(parents=True, exist_ok=True)
    test_file = att_dir / "test_plot.png"
    test_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRtest")

    try:
        resp = client.get("/attachments/test_plot.png")
        assert resp.status_code == 200
        assert resp.content == b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRtest"
    finally:
        if test_file.exists():
            test_file.unlink()


def test_agent_handle_audio_streaming_callback():
    """Verify handle_audio pipes completed sentences to on_sentence callback."""
    mock_provider = MagicMock(spec=GeminiProvider)
    mock_provider.is_configured.return_value = True

    # Simulate streaming tokens
    def _mock_audio_stream(prompt, audio_bytes):
        yield "System operational, "
        yield "sir. "
        yield "All engineering telemetry "
        yield "is nominal."

    mock_provider.generate_with_audio_stream = _mock_audio_stream

    agent = FridayAgent(gemini_provider=mock_provider)

    received_sentences = []
    def on_sent(s):
        received_sentences.append(s)

    reply = agent.handle_audio(b"mock_wav", on_sentence=on_sent)
    assert len(received_sentences) == 2
    assert "System operational, sir." in received_sentences[0]
    assert "All engineering telemetry is nominal." in received_sentences[1]
