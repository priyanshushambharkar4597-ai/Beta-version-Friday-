"""HUD Overlay Window - pywebview borderless translucent desktop window."""

from __future__ import annotations

import logging
import threading
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
        """Initialize pywebview window."""
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
                background_color="#00000000",
                js_api=HUDJsApi(self),
            )
            self._is_visible = True
        except Exception as exc:
            logger.warning(f"Failed to create pywebview window: {exc}")
            self.window = None

    def show(self) -> None:
        """Display the HUD window."""
        if self.window:
            try:
                self.window.show()
                self._is_visible = True
            except Exception:
                pass

    def hide(self) -> None:
        """Hide the HUD window."""
        if self.window:
            try:
                self.window.hide()
                self._is_visible = False
            except Exception:
                pass

    def toggle(self) -> None:
        """Toggle HUD window visibility."""
        if self._is_visible:
            self.hide()
        else:
            self.show()

    def start_loop(self) -> None:
        """Start pywebview event loop (blocking or in dedicated thread)."""
        try:
            import webview
            webview.start(debug=False)
        except Exception as exc:
            logger.warning(f"pywebview event loop ended or failed: {exc}")
