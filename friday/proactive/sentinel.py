"""Hardware & Workspace Ambient Sentinel for Friday."""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional, Set

import serial.tools.list_ports

from friday.event_bus import SystemEventBus, SystemEvent, EventType
from friday.tools.builtin.vision_tools import get_active_window_context

ENGINEERING_APPS = {
    "matlab": "MATLAB",
    "ltspice": "LTspice",
    "kicad": "KiCad EDA",
    "visual studio code": "VS Code",
    "altium": "Altium Designer",
    "quartus": "Intel Quartus Prime",
    "vivado": "Xilinx Vivado",
}


class FridaySentinel:
    """Proactive background monitor detecting hardware COM plugs and workspace engineering events."""

    def __init__(
        self,
        event_bus: Optional[SystemEventBus] = None,
        poll_interval: float = 10.0,
    ) -> None:
        """Initialize FridaySentinel.

        Args:
            event_bus: SystemEventBus instance to publish detected events.
            poll_interval: Seconds between background polling loops (default: 10s).
        """
        self.event_bus = event_bus or SystemEventBus()
        self.poll_interval = poll_interval
        self._known_ports: Set[str] = set()
        self._last_active_window: str = ""
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Seed initial COM ports
        self._seed_ports()

    def _seed_ports(self) -> None:
        """Record current COM ports so initial startup doesn't trigger spurious notifications."""
        try:
            current = {p.device for p in serial.tools.list_ports.comports()}
            self._known_ports = current
        except Exception:
            self._known_ports = set()

    def poll_step(self) -> Dict[str, Any]:
        """Perform a single CPU-only scan cycle for hardware and window state changes."""
        changes: Dict[str, Any] = {"new_devices": [], "removed_devices": [], "app_context": None}

        # 1. Hardware Serial COM Port Detection
        try:
            current_ports = {p.device: p.description for p in serial.tools.list_ports.comports()}
            current_set = set(current_ports.keys())

            added = current_set - self._known_ports
            removed = self._known_ports - current_set

            for port in added:
                desc = current_ports.get(port, "Serial Device")
                msg = f"Device detected on {port} ({desc}). Ready to monitor."
                changes["new_devices"].append({"port": port, "description": desc})
                self.event_bus.publish(
                    SystemEvent(
                        event_type=EventType.STATUS_CHANGE,
                        source="sentinel",
                        payload={"event": "device_connected", "port": port, "description": desc, "message": msg},
                    )
                )

            for port in removed:
                changes["removed_devices"].append(port)
                self.event_bus.publish(
                    SystemEvent(
                        event_type=EventType.STATUS_CHANGE,
                        source="sentinel",
                        payload={"event": "device_disconnected", "port": port},
                    )
                )

            self._known_ports = current_set
        except Exception:
            pass

        # 2. Active Window Contextual Guard
        try:
            win_ctx = get_active_window_context()
            win_title = win_ctx.get("title", "")
            if win_title and win_title != self._last_active_window:
                self._last_active_window = win_title
                lower_title = win_title.lower()

                # Check if focused app is an engineering environment
                matched_app = None
                for app_key, app_label in ENGINEERING_APPS.items():
                    if app_key in lower_title:
                        matched_app = app_label
                        break

                if matched_app:
                    has_error = any(term in lower_title for term in ("error", "exception", "failed", "syntax", "panic"))
                    payload = {
                        "event": "workspace_context",
                        "app": matched_app,
                        "window_title": win_title,
                        "rect": win_ctx.get("rect"),
                        "has_error_state": has_error,
                    }
                    changes["app_context"] = payload
                    self.event_bus.publish(
                        SystemEvent(
                            event_type=EventType.STATUS_CHANGE,
                            source="sentinel",
                            payload=payload,
                        )
                    )
        except Exception:
            pass

        return changes

    def _loop(self) -> None:
        """Worker loop running on a background daemon thread."""
        while not self._stop_event.is_set():
            self.poll_step()
            self._stop_event.wait(self.poll_interval)

    def start(self) -> None:
        """Start the background sentinel monitor thread."""
        if self._thread is None or not self._thread.is_alive():
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._loop, name="FridaySentinel", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop the background sentinel thread."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def is_running(self) -> bool:
        """Check if sentinel worker is running."""
        return bool(self._thread and self._thread.is_alive())
