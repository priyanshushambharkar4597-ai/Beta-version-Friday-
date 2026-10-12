"""Unit tests for GeminiProvider adapter."""

import pytest
from unittest.mock import MagicMock, patch
from friday.llm.gemini_provider import GeminiProvider


def test_gemini_provider_unconfigured():
    provider = GeminiProvider(api_key=None)
    # When api_key is None and env var is empty
    if not provider.api_key:
        assert provider.is_configured() is False
        with pytest.raises(ValueError) as exc:
            provider.generate("Hello")
        assert "GEMINI_API_KEY" in str(exc.value)


@patch("friday.llm.gemini_provider.genai.configure")
@patch("friday.llm.gemini_provider.genai.GenerativeModel")
def test_gemini_provider_configured(mock_model_cls, mock_configure):
    mock_instance = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Hello boss, Friday is online."
    mock_instance.generate_content.return_value = mock_response
    mock_model_cls.return_value = mock_instance

    provider = GeminiProvider(api_key="test_dummy_key_123")
    assert provider.is_configured() is True

    result = provider.generate("Greetings")
    assert result == "Hello boss, Friday is online."
    mock_configure.assert_called_once_with(api_key="test_dummy_key_123")


@patch("friday.llm.gemini_provider.genai.configure")
@patch("friday.llm.gemini_provider.genai.GenerativeModel")
def test_gemini_provider_chat(mock_model_cls, mock_configure):
    mock_instance = MagicMock()
    mock_chat_session = MagicMock()
    mock_chat_response = MagicMock()
    mock_chat_response.text = "System nominal."
    mock_chat_session.send_message.return_value = mock_chat_response
    mock_instance.start_chat.return_value = mock_chat_session
    mock_model_cls.return_value = mock_instance

    provider = GeminiProvider(api_key="test_dummy_key_123")
    res = provider.chat("Status report")
    assert res == "System nominal."
    mock_chat_session.send_message.assert_called_once_with("Status report")
