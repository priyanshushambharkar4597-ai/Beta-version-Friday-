"""Unit tests for Multimodal Screen Capture and Vision integration."""

from pathlib import Path
from unittest.mock import MagicMock
from PIL import Image
import pytest

from friday.llm.gemini_provider import GeminiProvider
from friday.tools.builtin.vision_tools import CaptureScreenTool


def test_capture_screen_tool(tmp_path: Path):
    save_dir = tmp_path / "screenshots"
    tool = CaptureScreenTool(save_dir=str(save_dir))

    res = tool.execute()
    assert res["status"] == "captured"
    assert Path(res["file_path"]).exists()
    assert res["width"] > 0
    assert res["height"] > 0
    assert res["file_path"].endswith(".png")
    assert "active_window" in res
    assert "title" in res["active_window"]


def test_gemini_provider_generate_with_image():
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "The screenshot displays an interactive Python IDE terminal."
    mock_model.generate_content.return_value = mock_response

    provider = GeminiProvider(api_key="test_key")
    provider._model = mock_model

    dummy_img = Image.new("RGB", (100, 100), color="blue")
    result = provider.generate_with_image("What is on screen?", dummy_img)

    assert result == "The screenshot displays an interactive Python IDE terminal."
    assert mock_model.generate_content.called
    call_args = mock_model.generate_content.call_args[0][0]
    assert call_args[0] == "What is on screen?"
    assert isinstance(call_args[1], Image.Image)
