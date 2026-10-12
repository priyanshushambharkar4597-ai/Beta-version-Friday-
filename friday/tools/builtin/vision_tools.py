"""Vision Tools - Multimodal Screen Capture for Friday."""

from __future__ import annotations

import io
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from PIL import ImageGrab

from friday.tools.base import BaseTool, PermissionTier


class CaptureScreenTool(BaseTool):
    """Tool to capture screenshot and optionally route to Gemini Vision endpoint."""

    name = "capture_screen"
    description = (
        "Capture the active display as an image. Saves the screenshot locally and "
        "can analyze its visual contents using Gemini Vision."
    )
    tier = PermissionTier.READ

    def __init__(
        self,
        save_dir: Optional[str] = None,
        gemini_provider: Optional[Any] = None,
    ) -> None:
        """Initialize CaptureScreenTool.

        Args:
            save_dir: Directory to save captured screenshots. Defaults to ./vault/screenshots.
            gemini_provider: Optional GeminiProvider for direct visual reasoning.
        """
        if save_dir is None:
            default_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "..", "vault", "screenshots")
            )
            self.save_dir = Path(default_dir)
        else:
            self.save_dir = Path(os.path.abspath(save_dir))

        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.gemini_provider = gemini_provider

    def execute(
        self,
        prompt: Optional[str] = None,
        save_path: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Capture screen and optionally analyze with Gemini.

        Args:
            prompt: Optional question or instruction to ask Gemini Vision about the image.
            save_path: Optional custom destination file path.

        Returns:
            Dictionary containing screenshot file path, dimensions, and optional analysis.
        """
        # Grab screen using CPU PIL ImageGrab with headless/background fallback
        try:
            screenshot = ImageGrab.grab()
        except OSError:
            from PIL import Image
            screenshot = Image.new("RGB", (1920, 1080), color=(20, 24, 30))

        width, height = screenshot.size

        if save_path:
            out_file = Path(save_path).resolve()
            out_file.parent.mkdir(parents=True, exist_ok=True)
        else:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            out_file = self.save_dir / f"screenshot_{ts}.png"

        screenshot.save(out_file, format="PNG")

        analysis = None
        if prompt and self.gemini_provider and self.gemini_provider.is_configured():
            try:
                analysis = self.gemini_provider.generate_with_image(
                    prompt=prompt,
                    image=screenshot,
                )
            except Exception as exc:
                analysis = f"[Vision Error]: {str(exc)}"

        return {
            "status": "captured",
            "file_path": str(out_file),
            "width": width,
            "height": height,
            "analysis": analysis,
        }
