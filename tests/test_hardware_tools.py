"""Unit tests for Hardware Serial Monitor and Datasheet tools."""

from unittest.mock import MagicMock, patch
import pytest

from friday.tools.builtin.datasheet_tools import SearchDatasheetTool
from friday.tools.builtin.hardware_tools import (
    ListSerialPortsTool,
    ReadSerialTelemetryTool,
)


def test_list_serial_ports_mocked():
    """Verify list_serial_ports enumerates connected devices cleanly."""
    mock_port = MagicMock()
    mock_port.device = "COM3"
    mock_port.description = "Silicon Labs CP210x USB to UART Bridge"
    mock_port.hwid = "USB VID:PID=10C4:EA60"
    mock_port.manufacturer = "Silicon Labs"

    with patch("serial.tools.list_ports.comports", return_value=[mock_port]):
        tool = ListSerialPortsTool()
        ports = tool.execute()

        assert len(ports) == 1
        assert ports[0]["port"] == "COM3"
        assert "CP210x" in ports[0]["description"]


def test_read_serial_telemetry_mocked():
    """Verify read_serial_telemetry buffers lines and safely closes the port."""
    mock_serial_instance = MagicMock()
    mock_serial_instance.in_waiting = 2
    mock_lines = [
        b"[SENSOR] Temperature: 24.5 C, Humidity: 55%\n",
        b"[TELEMETRY] Batt: 4.12V, Status: OK\n",
    ]

    def mock_readline():
        if mock_lines:
            return mock_lines.pop(0)
        mock_serial_instance.in_waiting = 0
        return b""

    mock_serial_instance.readline = mock_readline

    with patch("serial.Serial", return_value=mock_serial_instance):
        tool = ReadSerialTelemetryTool()
        res = tool.execute(port="COM4", baudrate=115200, duration_seconds=0.3)

        assert res["status"] == "success"
        assert res["port"] == "COM4"
        assert res["line_count"] >= 1
        assert "Temperature: 24.5 C" in res["telemetry"]
        mock_serial_instance.close.assert_called_once()


def test_read_serial_telemetry_port_open_error():
    """Verify graceful error reporting when serial port is unavailable or locked."""
    with patch("serial.Serial", side_effect=OSError("Access denied to COM1")):
        tool = ReadSerialTelemetryTool()
        res = tool.execute(port="COM1", duration_seconds=0.1)

        assert res["status"] == "error"
        assert "Could not open serial port" in res["error"]


def test_search_datasheet_catalog_lookup():
    """Verify datasheet search returns accurate engineering pinouts and electrical specs."""
    tool = SearchDatasheetTool()

    # 1. NE555 Timer
    res_555 = tool.execute(component_name="NE555")
    assert res_555["status"] == "found"
    assert "NE555" in res_555["component"]
    assert "4.5V to 16V" in res_555["supply_voltage"]
    assert "Discharge" in res_555["pinout"]

    # 2. LM741 Op-Amp
    res_741 = tool.execute(component_name="LM741")
    assert res_741["status"] == "found"
    assert "Non-Inverting" in res_741["pinout"]

    # 3. ESP32 Microcontroller
    res_esp = tool.execute(component_name="ESP32")
    assert res_esp["status"] == "found"
    assert "Xtensa" in res_esp["key_parameters"]["cpu"]

    # 4. Fallback search for unknown part
    res_custom = tool.execute(component_name="AD9850")
    assert res_custom["status"] == "generic_spec_lookup"
    assert "alldatasheet" in res_custom["datasheet_archive_url"]
