"""Unit tests for Friday's tiered safety permission gate."""

import pytest
from friday.agent import FridayAgent
from friday.tools.base import BaseTool, PermissionGate, PermissionTier


class MockReadTool(BaseTool):
    name = "mock_read"
    description = "Read mock file"
    tier = PermissionTier.READ

    def execute(self, path: str = "test.txt") -> str:
        return f"content of {path}"


class MockReversibleTool(BaseTool):
    name = "mock_reversible"
    description = "Create branch"
    tier = PermissionTier.REVERSIBLE

    def execute(self, branch: str = "dev") -> str:
        return f"created branch {branch}"


class MockIrreversibleTool(BaseTool):
    name = "mock_irreversible"
    description = "Run terminal command"
    tier = PermissionTier.IRREVERSIBLE

    def execute(self, cmd: str) -> str:
        return f"executed {cmd}"


def test_permission_gate_read_auto_authorizes():
    gate = PermissionGate()
    authorized = gate.check_and_authorize(
        tool_name="mock_read",
        tier=PermissionTier.READ,
        description="Reading test.txt",
        params={"path": "test.txt"},
    )
    assert authorized is True


def test_permission_gate_reversible_auto_authorizes():
    gate = PermissionGate()
    authorized = gate.check_and_authorize(
        tool_name="mock_reversible",
        tier=PermissionTier.REVERSIBLE,
        description="Creating branch",
        params={"branch": "dev"},
    )
    assert authorized is True


def test_permission_gate_irreversible_declined():
    gate = PermissionGate(confirm_callback=lambda name, desc, params: False)
    authorized = gate.check_and_authorize(
        tool_name="mock_irreversible",
        tier=PermissionTier.IRREVERSIBLE,
        description="Run bash",
        params={"cmd": "rm -rf /"},
    )
    assert authorized is False


def test_permission_gate_irreversible_approved():
    gate = PermissionGate(confirm_callback=lambda name, desc, params: True)
    authorized = gate.check_and_authorize(
        tool_name="mock_irreversible",
        tier=PermissionTier.IRREVERSIBLE,
        description="Run bash",
        params={"cmd": "dir"},
    )
    assert authorized is True


def test_agent_tool_execution_flow():
    # Setup agent with auto-approving gate for test
    gate = PermissionGate(confirm_callback=lambda name, desc, params: True)
    agent = FridayAgent(permission_gate=gate)

    read_tool = MockReadTool()
    irrev_tool = MockIrreversibleTool()

    agent.register_tool(read_tool)
    agent.register_tool(irrev_tool)

    # 1. READ tool runs cleanly
    res_read = agent.execute_tool("mock_read", {"path": "main.py"})
    assert res_read == "content of main.py"

    # 2. IRREVERSIBLE tool runs when approved
    res_irrev = agent.execute_tool("mock_irreversible", {"cmd": "pytest"})
    assert res_irrev == "executed pytest"

    # Verify audit log recorded entries
    assert len(gate.audit_log) == 2
    assert gate.audit_log[0].tool_name == "mock_read"
    assert gate.audit_log[0].approved is True
    assert gate.audit_log[1].tool_name == "mock_irreversible"
    assert gate.audit_log[1].approved is True


def test_agent_tool_execution_blocked_on_decline():
    # Setup agent with declining gate
    gate = PermissionGate(confirm_callback=lambda name, desc, params: False)
    agent = FridayAgent(permission_gate=gate)

    irrev_tool = MockIrreversibleTool()
    agent.register_tool(irrev_tool)

    with pytest.raises(PermissionError) as exc_info:
        agent.execute_tool("mock_irreversible", {"cmd": "format C:"})

    assert "declined" in str(exc_info.value).lower()
    assert len(gate.audit_log) == 1
    assert gate.audit_log[0].approved is False
