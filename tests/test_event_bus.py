"""Unit tests for Friday's SystemEventBus."""

import pytest
from friday.event_bus import EventType, SystemEvent, SystemEventBus


def test_system_event_bus_pub_sub():
    bus = SystemEventBus()

    received: list[SystemEvent] = []

    def on_text(event: SystemEvent):
        received.append(event)

    bus.subscribe(EventType.TEXT_INPUT, on_text)

    # Publish text event
    pub_event = bus.publish(
        event_type=EventType.TEXT_INPUT,
        payload={"text": "Hello Friday"},
        source="cli",
    )

    assert len(received) == 1
    assert received[0].payload["text"] == "Hello Friday"
    assert received[0].source == "cli"
    assert len(bus.history) == 1

    # Publish unrelated event
    bus.publish(
        event_type=EventType.SCREEN_CAPTURE,
        payload={"path": "screen.png"},
    )
    # on_text listener should not have triggered again
    assert len(received) == 1
    assert len(bus.history) == 2
