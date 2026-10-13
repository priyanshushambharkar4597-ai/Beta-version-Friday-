"""Background Event Scheduler & Proactive Routine Manager for Friday."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from friday.event_bus import SystemEventBus, SystemEvent, EventType
from friday.voice.tts import FridayTTS


class FridayScheduler:
    """Manages recurring cron routines, morning briefings, and quiet hours enforcements."""

    def __init__(
        self,
        event_bus: Optional[SystemEventBus] = None,
        tts: Optional[FridayTTS] = None,
        vault_dir: Optional[str] = None,
        briefing_hour: int = 8,
        briefing_minute: int = 0,
    ) -> None:
        """Initialize FridayScheduler.

        Args:
            event_bus: SystemEventBus instance for broadcasting reminders.
            tts: FridayTTS instance for spoken vocalizations.
            vault_dir: Path to Obsidian vault.
            briefing_hour: Hour for daily morning briefing (default: 8 AM).
            briefing_minute: Minute for daily morning briefing (default: 0).
        """
        self.event_bus = event_bus or SystemEventBus()
        self.tts = tts
        self.vault_dir = Path(vault_dir or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "vault")))
        self.briefing_hour = briefing_hour
        self.briefing_minute = briefing_minute

        self.scheduler = BackgroundScheduler(daemon=True)
        self._running = False

    def is_quiet_hours(self, target_dt: Optional[datetime] = None) -> bool:
        """Check whether the current time falls inside quiet hours (11:00 PM - 7:00 AM).

        Args:
            target_dt: Optional datetime to test. Defaults to local current time.

        Returns:
            True if quiet hours are active, False otherwise.
        """
        dt = target_dt or datetime.now()
        # Quiet hours: 23:00 (11 PM) through 06:59 (7 AM)
        return dt.hour >= 23 or dt.hour < 7

    def scan_vault_pending_tasks(self) -> List[str]:
        """Scan Obsidian vault notes for open Markdown checklist items (- [ ])."""
        pending_tasks: List[str] = []
        if not self.vault_dir.exists():
            return pending_tasks

        for md_file in self.vault_dir.glob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                for line in content.splitlines():
                    match = re.match(r"^\s*-\s*\[\s*\]\s*(.+)$", line)
                    if match:
                        task_text = match.group(1).strip()
                        pending_tasks.append(f"{md_file.stem}: {task_text}")
            except Exception:
                continue

        return pending_tasks

    def get_core_memory_projects(self) -> str:
        """Read active projects from vault/_core_memory.md if present."""
        core_file = self.vault_dir / "_core_memory.md"
        if not core_file.exists():
            return "Friday v1.1 engineering runtime"

        try:
            content = core_file.read_text(encoding="utf-8")
            match = re.search(r"## Active Projects\s*\n(.*?)(?=\n##|\Z)", content, re.DOTALL)
            if match:
                projects = match.group(1).strip().replace("\n", "; ")
                return projects
        except Exception:
            pass
        return "Friday v1.1 engineering runtime"

    def generate_morning_briefing(self) -> str:
        """Compile a concise, natural morning briefing report."""
        tasks = self.scan_vault_pending_tasks()
        projects = self.get_core_memory_projects()

        task_summary = f"You have {len(tasks)} open tasks in your vault." if tasks else "All vault checklists are clear."
        if tasks:
            top_tasks = tasks[:2]
            task_summary += f" Top items: {', '.join(top_tasks)}."

        briefing = (
            f"Good morning, Boss. Friday online. {task_summary} "
            f"Active projects: {projects}. Systems nominal, ready when you are."
        )
        return briefing

    def run_morning_briefing(self) -> str:
        """Execute morning briefing, broadcast event, and optionally vocalize."""
        briefing_text = self.generate_morning_briefing()

        # Emit to event bus
        self.event_bus.publish(
            SystemEvent(
                event_type=EventType.STATUS_CHANGE,
                source="scheduler",
                payload={"event": "morning_briefing", "text": briefing_text},
            )
        )

        # Vocalize aloud if not in quiet hours and TTS is configured
        if not self.is_quiet_hours() and self.tts is not None:
            try:
                self.tts.speak(briefing_text, async_playback=True)
            except Exception:
                pass

        return briefing_text

    def start(self) -> None:
        """Start the background scheduler."""
        if not self._running:
            self.scheduler.add_job(
                self.run_morning_briefing,
                CronTrigger(hour=self.briefing_hour, minute=self.briefing_minute),
                id="morning_briefing_job",
                replace_existing=True,
            )
            self.scheduler.start()
            self._running = True

    def shutdown(self) -> None:
        """Stop the background scheduler."""
        if self._running:
            try:
                self.scheduler.shutdown(wait=False)
            except Exception:
                pass
            self._running = False

    def is_running(self) -> bool:
        """Check if scheduler is actively running."""
        return self._running
