"""Vision Tools - Multimodal Screen Capture with Active Window Grounding for Friday."""

from __future__ import annotations

import ctypes
import io
import os
import sys
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from PIL import ImageGrab

from friday.tools.base import BaseTool, PermissionTier


def get_active_window_context() -> Dict[str, Any]:
    """Retrieve the title and geometry bounds of the active foreground window on Windows."""
    if sys.platform != "win32":
        return {"title": "Unknown", "rect": None}

    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return {"title": "Desktop / No Foreground Window", "rect": None}

        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip() or "Untitled Window"

        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        rect_dict = {
            "left": rect.left,
            "top": rect.top,
            "right": rect.right,
            "bottom": rect.bottom,
            "width": max(0, rect.right - rect.left),
            "height": max(0, rect.bottom - rect.top),
        }
        return {"title": title, "rect": rect_dict}
    except Exception:
        return {"title": "Unknown", "rect": None}


class CaptureScreenTool(BaseTool):
    """Tool to capture screenshot with active window context and optional Gemini Vision analysis."""

    name = "capture_screen"
    description = (
        "Capture the active display as an image with foreground window context metadata. "
        "Saves the screenshot locally and can analyze its visual contents using Gemini Vision."
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
            Dictionary containing screenshot file path, dimensions, active window info, and analysis.
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

        # Capture active window grounding metadata
        active_window = get_active_window_context()

        analysis = None
        if prompt and self.gemini_provider and self.gemini_provider.is_configured():
            window_title = active_window.get("title", "")
            enriched_prompt = (
                f"[Workspace Context: Active Window '{window_title}']\n{prompt}"
                if window_title and window_title != "Unknown"
                else prompt
            )
            try:
                analysis = self.gemini_provider.generate_with_image(
                    prompt=enriched_prompt,
                    image=screenshot,
                )
            except Exception as exc:
                analysis = f"[Vision Error]: {str(exc)}"

        return {
            "status": "captured",
            "file_path": str(out_file),
            "width": width,
            "height": height,
            "active_window": active_window,
            "analysis": analysis,
        }
