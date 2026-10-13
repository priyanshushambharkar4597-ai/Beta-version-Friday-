"""Microcontroller Serial Monitor & Hardware Telemetry Tools for Friday."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import serial
import serial.tools.list_ports

from friday.tools.base import BaseTool, PermissionTier


class ListSerialPortsTool(BaseTool):
    """Tool to discover and enumerate connected COM ports / microcontrollers."""

    name = "list_serial_ports"
    description = (
        "Scan active COM ports on Windows to discover connected microcontrollers "
        "(Arduino, ESP32, STM32, Raspberry Pi Pico, USB-UART bridges)."
    )
    tier = PermissionTier.READ

    def execute(self, **kwargs: Any) -> List[Dict[str, Any]]:
        """List all active hardware serial COM ports."""
        ports = serial.tools.list_ports.comports()
        detected: List[Dict[str, Any]] = []

        for p in ports:
            detected.append({
                "port": p.device,
                "description": p.description,
                "hwid": p.hwid,
                "manufacturer": getattr(p, "manufacturer", "Unknown"),
            })

        return detected


class ReadSerialTelemetryTool(BaseTool):
    """Tool to read live telemetry or crash logs from a microcontroller COM port."""

    name = "read_serial_telemetry"
    description = (
        "Read incoming serial telemetry, sensor data, or firmware debug crash logs "
        "from a specified COM port for a given duration."
    )
    tier = PermissionTier.REVERSIBLE

    def execute(
        self,
        port: str,
        baudrate: int = 115200,
        duration_seconds: float = 3.0,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Read serial stream from target port.

        Args:
            port: COM port identifier (e.g., 'COM3').
            baudrate: Communication baud rate (default: 115200).
            duration_seconds: Duration to sample incoming lines (default: 3.0).

        Returns:
            Dictionary with buffered output lines, line count, and port status.
        """
        lines: List[str] = []
        start_time = time.time()
        timeout = max(0.5, min(15.0, float(duration_seconds)))

        try:
            ser = serial.Serial(port=port, baudrate=baudrate, timeout=0.2)
        except Exception as exc:
            return {
                "status": "error",
                "port": port,
                "error": f"Could not open serial port {port}: {str(exc)}",
                "lines": [],
            }

        try:
            while time.time() - start_time < timeout:
                if ser.in_waiting:
                    raw_line = ser.readline()
                    line_str = raw_line.decode("utf-8", errors="replace").strip()
                    if line_str:
                        lines.append(line_str)
                else:
                    time.sleep(0.05)
        finally:
            try:
                ser.close()
            except Exception:
                pass

        return {
            "status": "success",
            "port": port,
            "baudrate": baudrate,
            "duration_seconds": timeout,
            "line_count": len(lines),
            "telemetry": "\n".join(lines) if lines else "[No serial data received within timeout window]",
            "lines": lines,
        }
