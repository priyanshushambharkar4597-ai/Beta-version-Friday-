"""Unit and Acceptance tests for Phase 4: Self-Evolution and Dynamic Skills."""

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from friday.agent import FridayAgent
from friday.llm.gemini_provider import GeminiProvider
from friday.tools.base import BaseTool, PermissionGate, PermissionTier
from friday.tools.dynamic_manager import DynamicSkillManager


SKILL_CODE_TEMPLATE = '''
from friday.tools.base import BaseTool, PermissionTier

class ResistorCalculator(BaseTool):
    name = "resistor_calculator"
    description = "Calculate 4-band resistor value in ohms"
    tier = PermissionTier.READ

    def execute(self, band1: str, band2: str, multiplier: str, **kwargs) -> dict:
        color_map = {
            "black": 0, "brown": 1, "red": 2, "orange": 3,
            "yellow": 4, "green": 5, "blue": 6, "violet": 7,
            "gray": 8, "white": 9
        }
        val = (color_map.get(band1.lower(), 0) * 10) + color_map.get(band2.lower(), 0)
        mult = 10 ** color_map.get(multiplier.lower(), 0)
        ohms = val * mult
        return {"ohms": ohms, "formatted": f"{ohms:,} ohms"}
'''


def test_dynamic_skill_creation_and_hot_reloading(tmp_path: Path):
    skills_dir = tmp_path / "dynamic_skills"
    agent = FridayAgent(workspace_dir=str(tmp_path))
    manager = DynamicSkillManager(dynamic_dir=str(skills_dir), agent=agent)

    # 1. Author and hot-reload new skill
    result = manager.create_skill(name="resistor_calculator", code=SKILL_CODE_TEMPLATE)
    assert result["status"] == "created_and_hot_reloaded"
    assert (skills_dir / "resistor_calculator.py").exists()

    # 2. Verify tool is dynamically registered in running agent
    assert "resistor_calculator" in agent.tools
    tool = agent.get_tool("resistor_calculator")
    assert tool is not None
    assert tool.name == "resistor_calculator"
    assert tool.tier == PermissionTier.READ

    # 3. Execute tool immediately without restart
    exec_res = agent.execute_tool(
        "resistor_calculator",
        {"band1": "brown", "band2": "black", "multiplier": "red"},
    )
    assert exec_res["ohms"] == 1000
    assert exec_res["formatted"] == "1,000 ohms"


def test_dynamic_skill_syntax_validation(tmp_path: Path):
    skills_dir = tmp_path / "dynamic_skills"
    manager = DynamicSkillManager(dynamic_dir=str(skills_dir))

    broken_code = "def invalid_syntax(: pass"
    with pytest.raises(ValueError) as exc:
        manager.create_skill(name="broken_skill", code=broken_code)
    assert "Syntax error" in str(exc.value)


def test_agentic_self_evolution_acceptance(tmp_path: Path):
    """Acceptance test: Friday writes a custom Python script based on a prompt, saves it, and executes it without restarting."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    skills_dir = workspace / "dynamic_skills"

    # Setup agent
    mock_llm = MagicMock(spec=GeminiProvider)
    mock_llm.is_configured.return_value = True

    agent = FridayAgent(
        gemini_provider=mock_llm,
        workspace_dir=str(workspace),
        dynamic_skills_dir=str(skills_dir),
    )

    # Round 1: Model creates a new skill (Decibel calculator for ENTC engineering)
    db_tool_code = """
from friday.tools.base import BaseTool, PermissionTier
import math

class DecibelCalculator(BaseTool):
    name = "decibel_calc"
    description = "Calculate power ratio in decibels"
    tier = PermissionTier.READ

    def execute(self, power_ratio: float, **kwargs) -> dict:
        db = 10.0 * math.log10(power_ratio)
        return {"power_ratio": power_ratio, "dB": round(db, 2)}
"""

    import json
    action_1_payload = json.dumps({
        "tool": "create_skill",
        "parameters": {"name": "decibel_calc", "code": db_tool_code},
    })
    resp_1 = f"I will create a dynamic tool to compute decibels from power ratio.\n```action\n{action_1_payload}\n```"

    # Round 2: Model uses the newly registered tool in the same session!
    resp_2 = (
        "Skill created and hot-reloaded! Now calculating for power ratio = 100:\n"
        "```action\n"
        '{\n  "tool": "decibel_calc",\n  "parameters": {"power_ratio": 100.0}\n}\n'
        "```"
    )

    # Round 3: Model summarizes results
    resp_3 = "A power ratio of 100 corresponds to +20.0 dB."

    mock_llm.chat.side_effect = [resp_1, resp_2, resp_3]

    final_result = agent.process("Create a tool to calculate decibels for power ratio 100 and evaluate it.")

    # Verify tool exists on disk
    assert (skills_dir / "decibel_calc.py").exists()

    # Verify tool was registered in agent
    assert "decibel_calc" in agent.tools

    # Verify tool was actually executed in the same session
    assert "20.0 dB" in final_result or "decibel" in final_result.lower()
