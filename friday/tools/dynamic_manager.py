"""The Jarvis Protocol - Dynamic Tool Creation & Hot-Reloading Engine for Friday."""

from __future__ import annotations

import ast
import importlib
import importlib.util
import inspect
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from friday.tools.base import BaseTool, PermissionTier


class DynamicSkillManager:
    """Manages authoring, discovery, and hot-reloading of self-evolved Python tools."""

    def __init__(
        self,
        dynamic_dir: Optional[str] = None,
        agent: Optional[Any] = None,
    ) -> None:
        """Initialize DynamicSkillManager.

        Args:
            dynamic_dir: Directory where dynamic skills are written.
            agent: FridayAgent instance whose tool registry will be updated on reload.
        """
        if dynamic_dir is None:
            default_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "dynamic")
            )
            self.dynamic_dir = Path(default_dir)
        else:
            self.dynamic_dir = Path(os.path.abspath(dynamic_dir))

        self.dynamic_dir.mkdir(parents=True, exist_ok=True)
        self.agent = agent
        self.loaded_tools: Dict[str, BaseTool] = {}

    def discover_and_load_all(self) -> List[BaseTool]:
        """Discover and hot-load all python tool modules in the dynamic skills folder."""
        loaded: List[BaseTool] = []
        for file_path in self.dynamic_dir.glob("*.py"):
            if file_path.name.startswith("__"):
                continue
            tools = self.load_module(file_path.stem)
            loaded.extend(tools)
        return loaded

    def load_module(self, module_name: str) -> List[BaseTool]:
        """Dynamically load or hot-reload a single python tool file.

        Args:
            module_name: Stem name of the python file (without .py).

        Returns:
            List of instantiated BaseTool instances found in the module.
        """
        file_path = self.dynamic_dir / f"{module_name}.py"
        if not file_path.exists():
            raise FileNotFoundError(f"Dynamic skill file not found: {file_path}")

        full_module_name = f"friday.tools.dynamic.{module_name}"

        # If already imported, invalidate cache and reload
        spec = importlib.util.spec_from_file_location(full_module_name, str(file_path))
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not create import spec for {file_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[full_module_name] = module
        spec.loader.exec_module(module)

        # Inspect module for BaseTool subclasses
        found_tools: List[BaseTool] = []
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                inspect.isclass(attr)
                and issubclass(attr, BaseTool)
                and attr is not BaseTool
            ):
                try:
                    tool_instance = attr()
                    found_tools.append(tool_instance)
                    self.loaded_tools[tool_instance.name] = tool_instance

                    # Hot-register in agent if attached
                    if self.agent is not None:
                        self.agent.register_tool(tool_instance)
                        self.agent._update_system_instructions()
                except Exception as exc:
                    print(f"[Dynamic Skill Warning] Could not instantiate tool {attr_name}: {exc}")

        return found_tools

    def create_skill(
        self,
        name: str,
        code: str,
    ) -> Dict[str, Any]:
        """Author, save, and hot-reload a new custom Python skill on the fly.

        Args:
            name: Alphanumeric identifier for the skill (e.g., 'resistor_color_code').
            code: Complete Python source code subclassing BaseTool.

        Returns:
            Dictionary with creation and registration status.
        """
        # 1. Static AST validation to catch syntax errors before writing to disk
        try:
            ast.parse(code)
        except SyntaxError as syn_err:
            raise ValueError(f"Syntax error in dynamic tool code: {syn_err}")

        # 2. Write code to dynamic directory
        clean_name = name.strip().lower().replace("-", "_")
        target_file = self.dynamic_dir / f"{clean_name}.py"
        target_file.write_text(code, encoding="utf-8")

        # 3. Hot-reload module into running process
        tools = self.load_module(clean_name)
        if not tools:
            raise ValueError(
                f"File written to {target_file}, but no BaseTool subclass was found or instantiated."
            )

        tool_details = [
            {"name": t.name, "tier": t.tier.value, "description": t.description}
            for t in tools
        ]

        return {
            "status": "created_and_hot_reloaded",
            "module": clean_name,
            "path": str(target_file),
            "tools_registered": tool_details,
        }


class CreateSkillTool(BaseTool):
    """Tool allowing Friday to author and hot-reload custom tools on the fly."""

    name = "create_skill"
    description = (
        "Author, save, and hot-reload a new custom Python skill/tool into Friday's "
        "registry without restarting. Code must define a class inheriting from BaseTool."
    )
    tier = PermissionTier.REVERSIBLE

    def __init__(self, manager: DynamicSkillManager) -> None:
        self.manager = manager

    def execute(self, name: str, code: str, **kwargs: Any) -> Dict[str, Any]:
        return self.manager.create_skill(name=name, code=code)
