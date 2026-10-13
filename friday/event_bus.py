"""System Event Bus - Central Nervous System for Friday's Senses and Hands."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class EventType(str, Enum):
    """Core event categories routed through Friday's event bus."""
    TEXT_INPUT = "TEXT_INPUT"
    VOICE_INPUT = "VOICE_INPUT"
    SCREEN_CAPTURE = "SCREEN_CAPTURE"
    TOOL_ACTION = "TOOL_ACTION"
    TOOL_OBSERVATION = "TOOL_OBSERVATION"
    RESPONSE_GENERATED = "RESPONSE_GENERATED"
    AUDIT_EVENT = "AUDIT_EVENT"
    MEMORY_STORED = "MEMORY_STORED"
    STATUS_CHANGE = "STATUS_CHANGE"


@dataclass
class SystemEvent:
    """Discrete message unit delivered across the system event bus."""
    event_type: EventType
    payload: Dict[str, Any]
    source: str = "system"
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class SystemEventBus:
    """Decoupled Publish/Subscribe event bus for Friday's local body and cloud brain."""

    def __init__(self) -> None:
        self.listeners: Dict[EventType, List[Callable[[SystemEvent], None]]] = {
            t: [] for t in EventType
        }
        self.history: List[SystemEvent] = []

    def subscribe(
        self,
        event_type: EventType,
        callback: Callable[[SystemEvent], None],
    ) -> None:
        """Register an event listener callback."""
        if event_type not in self.listeners:
            self.listeners[event_type] = []
        self.listeners[event_type].append(callback)

    def publish(
        self,
        event_type: EventType | SystemEvent,
        payload: Optional[Dict[str, Any]] = None,
        source: str = "system",
    ) -> SystemEvent:
        """Publish an event synchronously to all registered listeners."""
        if isinstance(event_type, SystemEvent):
            event = event_type
            target_type = event.event_type
        else:
            target_type = event_type
            event = SystemEvent(event_type=target_type, payload=payload or {}, source=source)

        self.history.append(event)

        for callback in self.listeners.get(target_type, []):
            try:
                callback(event)
            except Exception as exc:
                print(f"[EventBus Handler Error]: {exc}")

        return event

    def clear_history(self) -> None:
        """Reset event history."""
        self.history.clear()
