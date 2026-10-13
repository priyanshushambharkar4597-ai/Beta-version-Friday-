"""Friday System Tray & Desktop Ambient Daemon."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw

from friday.ui.overlay import HUDOverlay
from friday.voice.tts import FridayTTS

logger = logging.getLogger("friday.system.tray")


def create_tray_icon_image() -> Image.Image:
    """Generate a sleek, futuristic cyan-and-gold Friday arc reactor icon."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Outer cyan ring
    draw.ellipse((4, 4, size - 4, size - 4), outline=(0, 240, 255, 255), width=4)
    # Inner gold ring
    draw.ellipse((14, 14, size - 14, size - 14), outline=(255, 183, 0, 220), width=3)
    # Glowing center core
    draw.ellipse((24, 24, size - 24, size - 24), fill=(0, 240, 255, 255))
    return img


class FridayTrayDaemon:
    """System Tray daemon managing background runtime, global hotkeys, and HUD."""

    def __init__(
        self,
        server_host: str = "127.0.0.1",
        server_port: int = 8000,
        enable_hotkeys: bool = True,
    ) -> None:
        self.server_host = server_host
        self.server_port = server_port
        self.enable_hotkeys = enable_hotkeys

        self.tts = FridayTTS()
        self.tts_muted = False
        self.running = False

        self.overlay = HUDOverlay(server_url=f"http://{server_host}:{server_port}/hud")
        self.tray_icon = None
        self._server_thread: Optional[threading.Thread] = None
        self._hotkey_listener = None

    def start_server_in_background(self) -> None:
        """Start the FastAPI uvicorn server in a daemon thread."""
        import uvicorn
        from friday.server import app

        def run_uvicorn():
            uvicorn.run(
                app,
                host=self.server_host,
                port=self.server_port,
                log_level="warning",
            )

        self._server_thread = threading.Thread(target=run_uvicorn, daemon=True)
        self._server_thread.start()
        # Brief pause to let server bind
        time.sleep(1.0)

    def setup_hotkeys(self) -> None:
        """Register global hotkeys with fail-soft fallback."""
        if not self.enable_hotkeys:
            return

        try:
            from pynput import keyboard

            def on_activate_hud():
                logger.info("Global hotkey triggered: Toggle HUD")
                self.overlay.toggle()

            def on_activate_voice():
                logger.info("Global hotkey triggered: Push-to-Talk")
                if not self.tts_muted:
                    self.tts.speak("Listening, boss.")

            # Register hotkeys for HUD and Voice
            hotkeys = keyboard.GlobalHotKeys({
                '<ctrl>+<alt>+f': on_activate_hud,
                '<ctrl>+<shift>+f': on_activate_hud,
                '<cmd>+<alt>+f': on_activate_hud,
                '<ctrl>+<space>': on_activate_voice,
                '<cmd>+<space>': on_activate_voice,
            })
            hotkeys.start()
            self._hotkey_listener = hotkeys
            logger.info("Global desktop hotkeys active: Ctrl+Alt+F / Win+Alt+F (HUD), Ctrl+Space (Voice)")
        except Exception as exc:
            logger.warning(
                f"Global hotkey hook could not be registered (fail-soft active): {exc}"
            )

    def toggle_hud(self, icon=None, item=None) -> None:
        """Open or toggle the Jarvis HUD window."""
        self.overlay.toggle()

    def toggle_mute(self, icon=None, item=None) -> None:
        """Toggle TTS audio feedback."""
        self.tts_muted = not self.tts_muted
        if not self.tts_muted:
            self.tts.speak("Voice output unmuted.")

    def open_obsidian_vault(self, icon=None, item=None) -> None:
        """Open Friday's Obsidian vault folder in Windows Explorer."""
        vault_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "vault")
        )
        if sys.platform == "win32":
            subprocess.Popen(["explorer.exe", vault_path])
        else:
            subprocess.Popen(["xdg-open", vault_path])

    def exit_app(self, icon=None, item=None) -> None:
        """Clean shutdown of background services, tray icon, and listeners."""
        self.running = False
        if self._hotkey_listener:
            try:
                self._hotkey_listener.stop()
            except Exception:
                pass

        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass

        logger.info("Friday desktop daemon shut down successfully.")
        sys.exit(0)

    def run(self) -> None:
        """Start the background server, hotkeys, and system tray loop."""
        import pystray
        from pystray import MenuItem as item

        self.running = True
        self.start_server_in_background()
        self.setup_hotkeys()

        # Initialize and immediately display HUD window
        self.overlay.create_window()
        try:
            self.overlay.show()
        except Exception as exc:
            logger.warning(f"Could not automatically show HUD: {exc}")

        # Vocalize startup greeting
        if not self.tts_muted:
            try:
                self.tts.speak("Hello Boss. Friday systems are online.")
            except Exception:
                pass

        # Build tray context menu
        menu = pystray.Menu(
            item("Open Friday HUD", self.toggle_hud, default=True),
            item(
                lambda text: "Unmute TTS" if self.tts_muted else "Mute TTS",
                self.toggle_mute,
            ),
            item("View Obsidian Vault", self.open_obsidian_vault),
            pystray.Menu.SEPARATOR,
            item("Exit Friday", self.exit_app),
        )

        icon_image = create_tray_icon_image()
        self.tray_icon = pystray.Icon(
            "FridayAI",
            icon_image,
            "Friday - Personal AI Assistant",
            menu=menu,
        )

        logger.info("Friday System Tray Daemon is running in background.")
        self.tray_icon.run()


def main() -> None:
    """CLI entrypoint to launch Friday desktop daemon."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    daemon = FridayTrayDaemon()
    daemon.run()


if __name__ == "__main__":
    main()
