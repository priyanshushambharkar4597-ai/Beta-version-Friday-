"""HUD Overlay Window - pywebview borderless translucent desktop window with fail-soft app fallback."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import webbrowser
from typing import Optional

logger = logging.getLogger("friday.ui.overlay")


class HUDOverlay:
    """Manages the borderless, semi-transparent desktop HUD spotlight overlay."""

    def __init__(
        self,
        server_url: str = "http://localhost:8000/hud",
        width: int = 860,
        height: int = 620,
    ) -> None:
        self.server_url = server_url
        self.width = width
        self.height = height
        self.window = None
        self._is_visible = False
        self._thread: Optional[threading.Thread] = None

    def create_window(self) -> None:
        """Initialize pywebview window with valid hex color triplet."""
        try:
            import webview

            class HUDJsApi:
                def __init__(self, overlay: HUDOverlay):
                    self.overlay = overlay

                def hide(self):
                    self.overlay.hide()

            self.window = webview.create_window(
                title="FRIDAY HUD",
                url=self.server_url,
                width=self.width,
                height=self.height,
                frameless=True,
                easy_drag=True,
                on_top=True,
                transparent=True,
                background_color="#000000",
                js_api=HUDJsApi(self),
            )
            self._is_visible = True
        except Exception as exc:
            logger.warning(f"Failed to create pywebview window: {exc}")
            self.window = None

    def show(self) -> None:
        """Display the HUD window."""
        if self.window and getattr(self.window, "gui", None) is not None:
            try:
                self.window.show()
                self._is_visible = True
                return
            except Exception:
                pass
        self.launch_app_window()

    def hide(self) -> None:
        """Hide the HUD window."""
        if self.window and getattr(self.window, "gui", None) is not None:
            try:
                self.window.hide()
                self._is_visible = False
                return
            except Exception:
                pass
        if hasattr(self, "_app_proc") and self._app_proc and self._app_proc.poll() is None:
            try:
                self._app_proc.terminate()
            except Exception:
                pass
            self._app_proc = None
            self._is_visible = False

    def toggle(self) -> None:
        """Toggle HUD window visibility, falling back to desktop app window."""
        if self.window and getattr(self.window, "gui", None) is not None:
            try:
                if self._is_visible:
                    self.hide()
                else:
                    self.show()
                return
            except Exception:
                pass
        else:
            if hasattr(self, "_app_proc") and self._app_proc and self._app_proc.poll() is None:
                self.hide()
                return
        self.launch_app_window()

    def launch_app_window(self) -> None:
        """Launch the HUD as a borderless standalone desktop window."""
        if hasattr(self, "_app_proc") and self._app_proc and self._app_proc.poll() is None:
            # Already active
            return

        edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        if sys.platform == "win32" and os.path.exists(edge_path):
            try:
                self._app_proc = subprocess.Popen([
                    edge_path,
                    f"--app={self.server_url}",
                    f"--window-size={self.width},{self.height}",
                ])
                self._is_visible = True
                return
            except Exception as exc:
                logger.warning(f"Failed to launch standalone Edge app window: {exc}")

        # Default browser fallback
        webbrowser.open(self.server_url)
        self._is_visible = True

    def start_loop(self) -> None:
        """Start pywebview event loop (blocking or in dedicated thread)."""
        try:
            import webview
            webview.start(debug=False)
        except Exception as exc:
            logger.warning(f"pywebview event loop ended or failed: {exc}")
