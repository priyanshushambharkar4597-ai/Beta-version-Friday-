"""Acceptance test for Phase 3: The Developer Workspace (Agentic Coding)."""

from pathlib import Path
import pytest
from unittest.mock import MagicMock

from friday.agent import FridayAgent
from friday.llm.gemini_provider import GeminiProvider
from friday.tools.base import PermissionGate, PermissionTier


def test_agentic_coding_bug_fix_and_permission_gate(tmp_path: Path):
    """Verify Friday can read a buggy python script, patch it, and prompt (Y/N) for bash execution."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # 1. Create buggy script
    buggy_file = workspace / "amplifier.py"
    buggy_file.write_text(
        "def calculate_gain(v_in: float, v_out: float) -> float:\n"
        "    # Bug: subtracted instead of divided\n"
        "    return v_in - v_out\n",
        encoding="utf-8",
    )

    # Track permission prompt calls
    prompted_actions = []

    def mock_user_gate(tool_name: str, description: str, params: dict) -> bool:
        prompted_actions.append({"tool": tool_name, "params": params})
        # Simulate user typing 'y'
        return True

    gate = PermissionGate(confirm_callback=mock_user_gate)

    # 2. Setup mock Gemini Cloud Brain sequence:
    # Round 1: Model asks to read the buggy file
    # Round 2: Model receives file content, emits patch action and test execution action
    # Round 3: Model summarizes fix
    mock_llm = MagicMock(spec=GeminiProvider)
    mock_llm.is_configured.return_value = True

    response_1 = (
        "I need to inspect the code first.\n"
        "```action\n"
        '{\n  "tool": "read_file",\n  "parameters": {"path": "amplifier.py"}\n}\n'
        "```"
    )

    response_2 = (
        "I identified the bug in calculate_gain (subtraction instead of division).\n"
        "Applying fix and running test:\n"
        "```action\n"
        '{\n  "tool": "patch_file",\n  "parameters": {"path": "amplifier.py", "target": "return v_in - v_out", "replacement": "return v_out / v_in"}\n}\n'
        "```\n"
        "```action\n"
        '{\n  "tool": "bash_execute",\n  "parameters": {"command": "Write-Output Verified"}\n}\n'
        "```"
    )

    response_3 = "Amplifier gain calculation has been fixed and verified."

    mock_llm.chat.side_effect = [response_1, response_2, response_3]

    agent = FridayAgent(
        gemini_provider=mock_llm,
        permission_gate=gate,
        workspace_dir=str(workspace),
    )

    # 3. Run agentic coding loop
    final_result = agent.process("Please fix the amplifier.py bug and verify.")

    # 4. Verify Acceptance Criteria:
    # A: File was read
    # B: File was patched on disk
    patched_content = buggy_file.read_text(encoding="utf-8")
    assert "return v_out / v_in" in patched_content
    assert "return v_in - v_out" not in patched_content

    # C: IRREVERSIBLE action triggered explicit permission confirmation
    assert len(prompted_actions) == 1
    assert prompted_actions[0]["tool"] == "bash_execute"
    assert "Verified" in prompted_actions[0]["params"]["command"]

    # D: Audit log recorded operations
    tool_names_logged = [r.tool_name for r in gate.audit_log]
    assert "read_file" in tool_names_logged
    assert "patch_file" in tool_names_logged
    assert "bash_execute" in tool_names_logged

    assert "Amplifier gain calculation has been fixed" in final_result


def test_agentic_coding_user_declines_irreversible_action(tmp_path: Path):
    """Verify that when a user says 'N' to an irreversible action, it is blocked and audited."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # User declines all IRREVERSIBLE actions
    gate = PermissionGate(confirm_callback=lambda name, desc, params: False)

    mock_llm = MagicMock(spec=GeminiProvider)
    mock_llm.is_configured.return_value = True

    response_1 = (
        "```action\n"
        '{\n  "tool": "bash_execute",\n  "parameters": {"command": "rmdir /s /q test"}\n}\n'
        "```"
    )
    response_2 = "Understood, command was cancelled by security gate."
    mock_llm.chat.side_effect = [response_1, response_2]

    agent = FridayAgent(
        gemini_provider=mock_llm,
        permission_gate=gate,
        workspace_dir=str(workspace),
    )

    res = agent.process("Delete the test folder")

    # Audit log should show bash_execute was NOT approved
    assert len(gate.audit_log) == 1
    assert gate.audit_log[0].tool_name == "bash_execute"
    assert gate.audit_log[0].approved is False
    assert "cancelled" in res.lower() or "security" in res.lower()
