"""Unit tests for FridayAgent core orchestrator."""

from unittest.mock import MagicMock
from friday.agent import FridayAgent
from friday.llm.gemini_provider import GeminiProvider


def test_agent_unconfigured_guidance():
    mock_provider = MagicMock(spec=GeminiProvider)
    mock_provider.is_configured.return_value = False

    agent = FridayAgent(gemini_provider=mock_provider)
    response = agent.process("Hello Friday")

    assert "Configuration Required" in response
    assert "GEMINI_API_KEY" in response


def test_agent_delegates_to_cloud_brain():
    mock_provider = MagicMock(spec=GeminiProvider)
    mock_provider.is_configured.return_value = True
    mock_provider.chat.return_value = "Always a pleasure to assist, sir."

    agent = FridayAgent(gemini_provider=mock_provider)
    response = agent.process("How are you today?")

    assert response == "Always a pleasure to assist, sir."
    mock_provider.chat.assert_called_once_with("How are you today?")
