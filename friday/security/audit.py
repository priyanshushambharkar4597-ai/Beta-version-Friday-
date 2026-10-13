"""Structured Audit Logging & Secret Redaction Engine for Friday."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

SECRET_PATTERNS = [
    # Google AI Studio / Gemini API keys (AIzaSy...)
    (re.compile(r"AIza[0-9A-Za-z-_]{30,40}"), "[REDACTED_GEMINI_KEY]"),
    # OpenAI style keys (sk-...)
    (re.compile(r"sk-[0-9A-Za-z]{20,}"), "[REDACTED_OPENAI_KEY]"),
    # Bearer tokens
    (re.compile(r"Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
    # Generic env variable assignments (API_KEY=..., PASSWORD=..., etc.)
    (
        re.compile(r"(GEMINI_API_KEY|API_KEY|SECRET|PASSWORD|TOKEN)\s*=\s*['\"]?[^\s'\"]+['\"]?", re.IGNORECASE),
        r"\1=[REDACTED_SECRET]",
    ),
]


def redact_secrets(text: str) -> str:
    """Scrub sensitive credentials, tokens, and API keys from a text string.

    Args:
        text: Input string potentially containing secret keys.

    Returns:
        Sanitized string with secrets replaced by redaction placeholders.
    """
    if not isinstance(text, str):
        return text

    sanitized = text
    for pattern, replacement in SECRET_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def redact_dict(data: Any) -> Any:
    """Recursively redact secrets from dictionaries, lists, and strings."""
    if isinstance(data, dict):
        return {k: redact_dict(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [redact_dict(item) for item in data]
    elif isinstance(data, str):
        return redact_secrets(data)
    return data


class AuditLogger:
    """Structured append-only JSONL audit logger for tracking tool executions safely."""

    def __init__(self, log_dir: Optional[str] = None) -> None:
        """Initialize AuditLogger.

        Args:
            log_dir: Directory where audit.jsonl is saved. Defaults to ./data.
        """
        if log_dir is None:
            default_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "data")
            )
            self.log_dir = Path(default_dir)
        else:
            self.log_dir = Path(os.path.abspath(log_dir))

        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.audit_file = self.log_dir / "audit.jsonl"

    def log_execution(
        self,
        tool_name: str,
        tier: str,
        parameters: Dict[str, Any],
        latency_ms: float = 0.0,
        success: bool = True,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record an execution entry to audit.jsonl with scrubbed parameters.

        Args:
            tool_name: Name of tool executed.
            tier: Safety tier string (READ, REVERSIBLE, IRREVERSIBLE).
            parameters: Raw arguments passed to the tool.
            latency_ms: Elapsed execution time in milliseconds.
            success: Whether execution completed without errors.
            error: Optional error description string.

        Returns:
            The sanitized entry dictionary recorded to disk.
        """
        sanitized_params = redact_dict(parameters)
        sanitized_error = redact_secrets(error) if error else None

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool_name": tool_name,
            "tier": tier,
            "parameters": sanitized_params,
            "latency_ms": round(latency_ms, 2),
            "success": success,
            "error": sanitized_error,
        }

        try:
            with open(self.audit_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as exc:
            print(f"[Audit Log Warning]: Could not append to audit log: {exc}")

        return entry
