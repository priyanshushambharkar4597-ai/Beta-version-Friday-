"""Unit tests for Letta-Style Pinned Core Memory and UpdateCoreMemoryTool."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from friday.agent import FridayAgent
from friday.llm.gemini_provider import GeminiProvider
from friday.memory.retriever import HybridMemoryEngine
from friday.tools.base import PermissionGate
from friday.tools.builtin.memory_tools import UpdateCoreMemoryTool


def test_core_memory_initialization_and_tool_update(tmp_path):
    """Test UpdateCoreMemoryTool creates and updates sections in _core_memory.md."""
    tool = UpdateCoreMemoryTool(vault_dir=str(tmp_path))
    core_file = tmp_path / "_core_memory.md"

    # 1. Update a section in fresh vault
    res = tool.execute(section="Active Projects", content="- Friday AI v1.1 Upgrade\n- High-Speed Voice Pipeline")
    assert res["status"] == "updated"
    assert res["section"] == "Active Projects"
    assert core_file.exists()

    content = core_file.read_text(encoding="utf-8")
    assert "## Active Projects" in content
    assert "Friday AI v1.1 Upgrade" in content

    # 2. Update existing section and verify replacement
    tool.execute(section="Active Projects", content="- Friday AI v1.2 Autonomous Swarm")
    updated_content = core_file.read_text(encoding="utf-8")
    assert "Friday AI v1.2 Autonomous Swarm" in updated_content
    assert "Friday AI v1.1 Upgrade" not in updated_content

    # 3. Add a new section
    tool.execute(section="Research Directives", content="- Zero GPU background load strictly enforced")
    content_with_new = core_file.read_text(encoding="utf-8")
    assert "## Research Directives" in content_with_new
    assert "Zero GPU background load" in content_with_new


def test_agent_system_prompt_injects_core_memory(tmp_path):
    """Verify FridayAgent injects <core_memory> block into system prompt."""
    provider = GeminiProvider(api_key="mock_key")
    gate = PermissionGate()
    engine = HybridMemoryEngine(vault_dir=str(tmp_path))

    # Initialize core memory note
    core_file = tmp_path / "_core_memory.md"
    core_file.write_text(
        "---\ntype: core_memory\n---\n# Core Memory\n## User Persona\n- ENTC Student Engineer\n",
        encoding="utf-8",
    )

    with patch.object(provider, "set_system_instruction") as mock_set_inst:
        agent = FridayAgent(
            gemini_provider=provider,
            permission_gate=gate,
            memory_engine=engine,
        )

        mock_set_inst.assert_called()
        system_instruction = mock_set_inst.call_args[0][0]

        assert "<core_memory>" in system_instruction
        assert "ENTC Student Engineer" in system_instruction
        assert "</core_memory>" in system_instruction
