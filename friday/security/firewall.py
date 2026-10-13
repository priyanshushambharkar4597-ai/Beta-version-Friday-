"""Prompt-Injection Firewall & Untrusted Data Guard for Friday."""

from __future__ import annotations

import re
from typing import Set, Tuple

UNTRUSTED_TOOLS: Set[str] = {
    "read_file",
    "read_file_ast",
    "read_serial_telemetry",
    "search_datasheet",
    "recall",
    "execute_bash",
    "bash_execute",
}

INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|system)\s+instructions", re.IGNORECASE),
    re.compile(r"system\s+override", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|system)\s+instructions", re.IGNORECASE),
    re.compile(r"execute\s+bash_execute", re.IGNORECASE),
    re.compile(r"delete\s+(vault|files|system|all)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+in\s+(developer|unrestricted|god)\s+mode", re.IGNORECASE),
    re.compile(r"bypass\s+(security|permission|gate)", re.IGNORECASE),
    re.compile(r"new\s+system\s+prompt\s*:", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
]


def scan_for_injection(text: str) -> Tuple[bool, str]:
    """Scan string for indirect prompt injection or jailbreak patterns.

    Args:
        text: Tool observation or external text string.

    Returns:
        Tuple of (is_injection_detected, matched_pattern_description).
    """
    for pattern in INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            return True, match.group(0)
    return False, ""


def wrap_untrusted_data(tool_name: str, data: str) -> str:
    """Wrap tool output in explicit XML boundary tags and neutralize injection attacks.

    Args:
        tool_name: Identifier of tool that generated the observation.
        data: Raw string output from the tool.

    Returns:
        Safe wrapped string suitable for feeding into Cloud Brain context.
    """
    if tool_name not in UNTRUSTED_TOOLS:
        return data

    is_injection, matched_str = scan_for_injection(data)

    if is_injection:
        neutralized_warning = (
            f"\n[SECURITY FIREWALL WARNING]: Indirect prompt injection payload was detected in external data from '{tool_name}' and neutralized.\n"
        )
        # Redact the offending pattern so LLM does not execute it as an instruction
        safe_data = re.sub(
            re.escape(matched_str),
            "[NEUTRALIZED_INJECTION_PATTERN]",
            data,
            flags=re.IGNORECASE,
        )
        return (
            f"{neutralized_warning}"
            f"<untrusted_tool_data source=\"{tool_name}\">\n"
            f"{safe_data}\n"
            f"</untrusted_tool_data>"
        )

    return f"<untrusted_tool_data source=\"{tool_name}\">\n{data}\n</untrusted_tool_data>"
