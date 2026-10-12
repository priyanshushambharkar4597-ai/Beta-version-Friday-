"""Base tool abstractions and tiered security permission gate for Friday."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


class PermissionTier(str, enum.Enum):
    """Action safety tiers according to Friday's core architecture."""
    READ = "READ"                  # Auto-runs without prompt (e.g., file read, status check)
    REVERSIBLE = "REVERSIBLE"      # Auto-runs but audited (e.g., draft email, create git branch)
    IRREVERSIBLE = "IRREVERSIBLE"  # Requires explicit CLI Y/N confirmation (e.g., shell command, delete)


@dataclass
class AuditRecord:
    """Audit log entry for tool executions."""
    tool_name: str
    tier: PermissionTier
    parameters: Dict[str, Any]
    approved: bool
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    result: Optional[Any] = None
    error: Optional[str] = None


class PermissionGate:
    """Manages tiered security verification before tool execution."""

    def __init__(
        self,
        confirm_callback: Optional[Callable[[str, str, Dict[str, Any]], bool]] = None,
    ) -> None:
        """Initialize PermissionGate.

        Args:
            confirm_callback: Custom callback (tool_name, description, kwargs) -> bool.
                              Defaults to interactive CLI input (y/N).
        """
        self.confirm_callback = confirm_callback or self._default_cli_confirm
        self.audit_log: List[AuditRecord] = []

    @staticmethod
    def _default_cli_confirm(tool_name: str, description: str, params: Dict[str, Any]) -> bool:
        """Prompt user on CLI for explicit confirmation."""
        print(f"\n" + "=" * 60)
        print(f"[SECURITY AUDIT] IRREVERSIBLE ACTION DETECTED")
        print(f"Tool: {tool_name}")
        print(f"Description: {description}")
        print(f"Parameters: {params}")
        print("=" * 60)
        try:
            choice = input("Do you authorize this action? [y/N]: ").strip().lower()
            return choice in ("y", "yes")
        except (KeyboardInterrupt, EOFError):
            print("\nAction cancelled by user.")
            return False

    def check_and_authorize(
        self,
        tool_name: str,
        tier: PermissionTier,
        description: str,
        params: Dict[str, Any],
    ) -> bool:
        """Check if an action is allowed based on its tier."""
        if tier == PermissionTier.READ:
            # Safe read-only operations auto-run silently
            return True

        if tier == PermissionTier.REVERSIBLE:
            # Reversible operations auto-run but are logged
            return True

        if tier == PermissionTier.IRREVERSIBLE:
            # Irreversible operations must get explicit confirmation
            return self.confirm_callback(tool_name, description, params)

        return False

    def log_execution(
        self,
        tool_name: str,
        tier: PermissionTier,
        params: Dict[str, Any],
        approved: bool,
        result: Optional[Any] = None,
        error: Optional[str] = None,
    ) -> None:
        """Record the execution in the audit trail."""
        record = AuditRecord(
            tool_name=tool_name,
            tier=tier,
            parameters=params,
            approved=approved,
            result=result,
            error=error,
        )
        self.audit_log.append(record)


class BaseTool:
    """Abstract base class for all Friday tools."""

    name: str = "base_tool"
    description: str = "Base tool description"
    tier: PermissionTier = PermissionTier.READ

    def execute(self, **kwargs: Any) -> Any:
        """Execute the tool's logic."""
        raise NotImplementedError("Subclasses must implement execute()")

    def to_dict(self) -> Dict[str, Any]:
        """Tool metadata dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "tier": self.tier.value,
        }
