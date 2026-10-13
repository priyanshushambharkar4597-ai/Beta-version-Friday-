"""Unit tests for Sandboxed Dynamic Skill 3-Stage Verification Pipeline."""

import pytest
from friday.tools.dynamic_manager import DynamicSkillManager


def test_dynamic_skill_ast_rejection_for_non_basetool(tmp_path):
    """Verify Stage 1 AST check rejects code that does not subclass BaseTool."""
    manager = DynamicSkillManager(dynamic_dir=str(tmp_path))

    non_tool_code = """
class SimpleHelper:
    def greet(self):
        return "Hello"
"""
    with pytest.raises(ValueError) as exc:
        manager.create_skill(name="non_tool", code=non_tool_code)
    assert "inheriting from 'BaseTool'" in str(exc.value)


def test_dynamic_skill_subprocess_dry_run_rejection(tmp_path):
    """Verify Stage 2 isolated subprocess catches crash before copying to dynamic dir."""
    manager = DynamicSkillManager(dynamic_dir=str(tmp_path))

    # Code that defines BaseTool subclass, but crashes upon instantiation or self_test
    crashing_code = """
from friday.tools.base import BaseTool, PermissionTier

class CrashingTool(BaseTool):
    name = "crashing_tool"
    description = "A tool that crashes during execution."
    tier = PermissionTier.READ

    def __init__(self):
        # Crash on instantiation
        raise RuntimeError("Fatal initialization bug in skill code")

    def execute(self, **kwargs):
        return {}
"""
    with pytest.raises(ValueError) as exc:
        manager.create_skill(name="crashing_tool", code=crashing_code)
    assert "dry-run verification failed" in str(exc.value)

    # Confirm broken file was NOT written to the dynamic skills directory
    target_file = tmp_path / "crashing_tool.py"
    assert not target_file.exists()


def test_dynamic_skill_valid_3_stage_acceptance(tmp_path):
    """Verify valid skill passes all 3 stages: AST -> Subprocess Dry Run -> Hot Reload."""
    manager = DynamicSkillManager(dynamic_dir=str(tmp_path))

    valid_tool_code = """
from typing import Any, Dict
from friday.tools.base import BaseTool, PermissionTier

class VoltageDividerTool(BaseTool):
    name = "voltage_divider"
    description = "Compute output voltage of an unloaded resistive voltage divider."
    tier = PermissionTier.READ

    def self_test(self):
        # Self test verified during dry-run
        res = self.execute(vin=10.0, r1=1000.0, r2=1000.0)
        assert res["vout"] == 5.0

    def execute(self, vin: float, r1: float, r2: float, **kwargs: Any) -> Dict[str, Any]:
        vout = vin * (r2 / (r1 + r2))
        return {"vout": vout, "attenuation_ratio": r2 / (r1 + r2)}
"""

    res = manager.create_skill(name="voltage_divider", code=valid_tool_code)
    assert res["status"] == "created_and_hot_reloaded"
    assert res["module"] == "voltage_divider"

    target_file = tmp_path / "voltage_divider.py"
    assert target_file.exists()

    # Tool is instantiated and executable
    tool = manager.loaded_tools.get("voltage_divider")
    assert tool is not None
    output = tool.execute(vin=12.0, r1=2000.0, r2=1000.0)
    assert round(output["vout"], 2) == 4.0
