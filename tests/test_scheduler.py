"""Unit tests for Friday Proactive Scheduler and Ambient Sentinel."""

from datetime import datetime
from unittest.mock import MagicMock, patch
import pytest

from friday.event_bus import SystemEventBus, EventType
from friday.proactive.scheduler import FridayScheduler
from friday.proactive.sentinel import FridaySentinel


def test_scheduler_quiet_hours_enforcer():
    """Verify quiet hours enforcement between 23:00 and 07:00."""
    scheduler = FridayScheduler()

    # 11:30 PM (23:30) -> Quiet
    dt_night = datetime(2026, 10, 14, 23, 30)
    assert scheduler.is_quiet_hours(dt_night) is True

    # 3:15 AM (03:15) -> Quiet
    dt_early = datetime(2026, 10, 14, 3, 15)
    assert scheduler.is_quiet_hours(dt_early) is True

    # 8:00 AM (08:00) -> Active
    dt_morning = datetime(2026, 10, 14, 8, 0)
    assert scheduler.is_quiet_hours(dt_morning) is False

    # 2:00 PM (14:00) -> Active
    dt_afternoon = datetime(2026, 10, 14, 14, 0)
    assert scheduler.is_quiet_hours(dt_afternoon) is False


def test_scheduler_vault_task_scanning_and_briefing(tmp_path):
    """Verify scanning open checklist items in vault notes and building morning report."""
    bus = SystemEventBus()
    scheduler = FridayScheduler(event_bus=bus, vault_dir=str(tmp_path))

    # Create mock task note
    task_note = tmp_path / "DSP-Lab.md"
    task_note.write_text(
        "# DSP Lab Notes\n"
        "- [x] Measure Butterworth attenuation\n"
        "- [ ] Calculate FFT on ESP32 signal\n"
        "- [ ] Submit lab report\n",
        encoding="utf-8",
    )

    tasks = scheduler.scan_vault_pending_tasks()
    assert len(tasks) == 2
    assert any("Calculate FFT" in t for t in tasks)

    briefing = scheduler.generate_morning_briefing()
    assert "Good morning, Boss" in briefing
    assert "2 open tasks" in briefing

    # Test run_morning_briefing publishes to event bus
    received_events = []
    bus.subscribe(EventType.STATUS_CHANGE, lambda ev: received_events.append(ev))

    with patch.object(scheduler, "is_quiet_hours", return_value=True):
        res = scheduler.run_morning_briefing()
        assert "Good morning" in res
        assert len(received_events) == 1
        assert received_events[0].payload["event"] == "morning_briefing"


def test_sentinel_com_port_change_detection():
    """Verify sentinel detects new hardware COM ports and publishes connected event."""
    bus = SystemEventBus()
    sentinel = FridaySentinel(event_bus=bus)

    # Initial known ports empty
    sentinel._known_ports = {"COM1"}

    # Mock new device plugged in (COM3)
    mock_p1 = MagicMock()
    mock_p1.device = "COM1"
    mock_p1.description = "Communications Port"

    mock_p2 = MagicMock()
    mock_p2.device = "COM3"
    mock_p2.description = "ESP32-S3 USB JTAG/serial"

    events = []
    bus.subscribe(EventType.STATUS_CHANGE, lambda ev: events.append(ev))

    with patch("serial.tools.list_ports.comports", return_value=[mock_p1, mock_p2]):
        changes = sentinel.poll_step()

        assert len(changes["new_devices"]) == 1
        assert changes["new_devices"][0]["port"] == "COM3"
        assert len(events) == 1
        assert events[0].payload["event"] == "device_connected"
        assert "Device detected on COM3" in events[0].payload["message"]
