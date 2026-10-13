"""Unit tests for Windows Autostart Persistence Manager."""

from pathlib import Path
import pytest

from friday.system.autostart import (
    DisableAutostartTool,
    EnableAutostartTool,
    GetAutostartStatusTool,
    disable_autostart,
    enable_autostart,
    get_autostart_status,
)


def test_autostart_lifecycle(tmp_path: Path):
    """Verify enabling, querying, and disabling autostart VBS launcher."""
    startup_dir = tmp_path / "Startup"
    startup_dir.mkdir(parents=True, exist_ok=True)

    # 1. Initially disabled
    assert get_autostart_status(startup_dir) is False

    # 2. Enable autostart
    res_enable = enable_autostart(project_dir=str(tmp_path), startup_dir=startup_dir)
    assert res_enable["status"] == "enabled"
    assert res_enable["headless"] is True
    assert get_autostart_status(startup_dir) is True

    vbs_file = startup_dir / "FridayAI.vbs"
    assert vbs_file.exists()
    content = vbs_file.read_text(encoding="utf-8")
    assert "WScript.Shell" in content
    assert "friday.system.tray" in content

    # 3. Disable autostart
    res_disable = disable_autostart(startup_dir=startup_dir)
    assert res_disable["status"] == "disabled"
    assert res_disable["removed"] is True
    assert not vbs_file.exists()
    assert get_autostart_status(startup_dir) is False


def test_autostart_tools_integration(tmp_path: Path):
    """Verify tool classes invoke autostart functionality cleanly."""
    enable_tool = EnableAutostartTool()
    status_tool = GetAutostartStatusTool()
    disable_tool = DisableAutostartTool()

    # Query status tool
    res_status = status_tool.execute()
    assert "autostart_enabled" in res_status
    assert isinstance(res_status["autostart_enabled"], bool)
