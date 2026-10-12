"""Unit tests for Friday System Tray daemon and icon generation."""

import pytest
from PIL import Image

from friday.system.tray import FridayTrayDaemon, create_tray_icon_image


def test_create_tray_icon_image():
    icon = create_tray_icon_image()
    assert isinstance(icon, Image.Image)
    assert icon.size == (64, 64)
    assert icon.mode == "RGBA"


def test_tray_daemon_initialization():
    daemon = FridayTrayDaemon(enable_hotkeys=False)
    assert daemon.tts_muted is False
    assert daemon.server_port == 8000

    # Toggle mute
    daemon.toggle_mute()
    assert daemon.tts_muted is True
    daemon.toggle_mute()
    assert daemon.tts_muted is False


def test_tray_daemon_fail_soft_hotkeys():
    daemon = FridayTrayDaemon(enable_hotkeys=True)
    # Should initialize or log warning gracefully without throwing unhandled exception
    try:
        daemon.setup_hotkeys()
    except Exception as exc:
        pytest.fail(f"setup_hotkeys raised unhandled exception: {exc}")
