"""Windows Autostart Persistence Manager for Friday."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from friday.tools.base import BaseTool, PermissionTier


def get_windows_startup_dir() -> Path:
    """Return the Windows user Startup folder path."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        startup_dir = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    else:
        startup_dir = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return startup_dir


def get_autostart_vbs_path(startup_dir: Optional[Path] = None) -> Path:
    """Return the path to Friday's headless autostart VBScript."""
    folder = startup_dir or get_windows_startup_dir()
    return folder / "FridayAI.vbs"


def enable_autostart(
    project_dir: Optional[str] = None,
    startup_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Create a headless autostart launcher in the Windows Startup folder.

    Args:
        project_dir: Root directory of Friday codebase.
        startup_dir: Optional custom startup directory for testing.

    Returns:
        Dictionary with status and shortcut path.
    """
    root = Path(project_dir or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))).resolve()
    target_vbs = get_autostart_vbs_path(startup_dir)
    target_vbs.parent.mkdir(parents=True, exist_ok=True)

    python_exe = root / ".venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        python_exe = Path(sys.executable)

    # Headless VBS script (window style 0 = completely hidden, no console flicker)
    vbs_content = (
        'Set WshShell = CreateObject("WScript.Shell")\n'
        f'WshShell.CurrentDirectory = "{str(root)}"\n'
        f'WshShell.Run """{str(python_exe)}"" -m friday.system.tray", 0, False\n'
    )

    target_vbs.write_text(vbs_content, encoding="utf-8")

    return {
        "status": "enabled",
        "file_path": str(target_vbs),
        "target_command": f'"{str(python_exe)}" -m friday.system.tray',
        "headless": True,
    }


def disable_autostart(startup_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Remove Friday's autostart launcher from Windows Startup."""
    target_vbs = get_autostart_vbs_path(startup_dir)
    removed = False
    if target_vbs.exists():
        try:
            target_vbs.unlink()
            removed = True
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    return {
        "status": "disabled",
        "removed": removed,
        "file_path": str(target_vbs),
    }


def get_autostart_status(startup_dir: Optional[Path] = None) -> bool:
    """Check whether Friday is configured to start on Windows boot."""
    target_vbs = get_autostart_vbs_path(startup_dir)
    return target_vbs.exists()


class EnableAutostartTool(BaseTool):
    """Tool to configure Friday to automatically run silently on Windows login."""

    name = "enable_autostart"
    description = (
        "Configure Friday to automatically launch silently in the background on Windows boot "
        "via a headless shortcut in the Startup folder."
    )
    tier = PermissionTier.REVERSIBLE

    def execute(self, **kwargs: Any) -> Dict[str, Any]:
        return enable_autostart()


class DisableAutostartTool(BaseTool):
    """Tool to remove Friday from Windows Startup."""

    name = "disable_autostart"
    description = "Remove Friday from Windows Startup so it no longer launches automatically on boot."
    tier = PermissionTier.REVERSIBLE

    def execute(self, **kwargs: Any) -> Dict[str, Any]:
        return disable_autostart()


class GetAutostartStatusTool(BaseTool):
    """Tool to check if Friday is registered to start on Windows boot."""

    name = "get_autostart_status"
    description = "Check whether Friday is currently configured to launch on Windows startup."
    tier = PermissionTier.READ

    def execute(self, **kwargs: Any) -> Dict[str, Any]:
        return {"autostart_enabled": get_autostart_status()}
