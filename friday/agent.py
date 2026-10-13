"""Friday Agent - Core Orchestrator for Friday."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from friday.llm.gemini_provider import GeminiProvider
from friday.memory.retriever import HybridMemoryEngine
from friday.tools.base import BaseTool, PermissionGate, PermissionTier
from friday.tools.builtin.coding_tools import (
    BashExecuteTool,
    PatchFileTool,
    ReadFileAstTool,
    ReadFileTool,
    WriteFileTool,
)
from friday.system.autostart import (
    DisableAutostartTool,
    EnableAutostartTool,
    GetAutostartStatusTool,
)
from friday.tools.builtin.datasheet_tools import SearchDatasheetTool
from friday.tools.builtin.hardware_tools import (
    ListSerialPortsTool,
    ReadSerialTelemetryTool,
)
from friday.tools.builtin.memory_tools import RecallTool, RememberTool, UpdateCoreMemoryTool
from friday.tools.builtin.repl_tool import PythonReplTool
from friday.tools.builtin.signal_lab import (
    AnalyzeTransferFunctionTool,
    DesignAnalogFilterTool,
)
from friday.tools.builtin.vision_tools import CaptureScreenTool
from friday.tools.dynamic_manager import CreateSkillTool, DynamicSkillManager


ACTION_PATTERN = re.compile(r"```(?:action|json:action)\s*(\{.*?\})\s*```", re.DOTALL)


class FridayAgent:
    """Core orchestrator managing the Cloud Brain and Local Body interactions."""

    def __init__(
        self,
        gemini_provider: Optional[GeminiProvider] = None,
        permission_gate: Optional[PermissionGate] = None,
        memory_engine: Optional[HybridMemoryEngine] = None,
        workspace_dir: Optional[str] = None,
        dynamic_skills_dir: Optional[str] = None,
    ) -> None:
        """Initialize the Friday Agent.

        Args:
            gemini_provider: Configured Gemini LLM client. If None, instantiates default.
            permission_gate: Tiered security permission gate. If None, instantiates default.
            memory_engine: Hybrid Obsidian vector + GraphRAG engine.
            workspace_dir: Base directory for local workspace files.
            dynamic_skills_dir: Directory for hot-reloaded dynamic skills.
        """
        self.workspace_dir = workspace_dir or os.getcwd()
        self.llm = gemini_provider or GeminiProvider()
        self.gate = permission_gate or PermissionGate()
        self.memory = memory_engine or HybridMemoryEngine()
        self.tools: Dict[str, BaseTool] = {}

        # Register Memory tools
        self.register_tool(RememberTool(self.memory))
        self.register_tool(RecallTool(self.memory))
        self.register_tool(UpdateCoreMemoryTool(memory_engine=self.memory))

        # Register Developer Workspace tools
        self.register_tool(ReadFileTool(self.workspace_dir))
        self.register_tool(ReadFileAstTool(self.workspace_dir))
        self.register_tool(WriteFileTool(self.workspace_dir))
        self.register_tool(PatchFileTool(self.workspace_dir))
        self.register_tool(BashExecuteTool(self.workspace_dir))
        self.register_tool(PythonReplTool())

        # Register Multimodal Vision tools
        self.register_tool(CaptureScreenTool(gemini_provider=self.llm))

        # Register ENTC Hardware & Signal Suite
        attachments_dir = str(self.memory.vault.vault_dir / "attachments") if hasattr(self.memory, "vault") else None
        self.register_tool(AnalyzeTransferFunctionTool(attachments_dir=attachments_dir))
        self.register_tool(DesignAnalogFilterTool())
        self.register_tool(ListSerialPortsTool())
        self.register_tool(ReadSerialTelemetryTool())
        self.register_tool(SearchDatasheetTool())

        # Register System Autostart tools
        self.register_tool(EnableAutostartTool())
        self.register_tool(DisableAutostartTool())
        self.register_tool(GetAutostartStatusTool())

        # Register Jarvis Protocol Dynamic Self-Evolution tools
        self.skill_manager = DynamicSkillManager(
            dynamic_dir=dynamic_skills_dir, agent=self
        )
        self.register_tool(CreateSkillTool(self.skill_manager))
        self.skill_manager.discover_and_load_all()

        self._update_system_instructions()

    def _get_core_memory_text(self) -> str:
        """Retrieve pinned core memory from Obsidian vault if present."""
        try:
            vault_dir = getattr(self.memory.vault, "vault_dir", None)
            if vault_dir:
                core_file = Path(vault_dir) / "_core_memory.md"
                if core_file.exists():
                    return core_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass
        return ""

    def _update_system_instructions(self) -> None:
        """Ensure the LLM provider has complete awareness of Friday's local body tools and core memory."""
        tool_docs = []
        for t in self.tools.values():
            tool_docs.append(f"- {t.name} [{t.tier.value}]: {t.description}")
        tools_str = "\n".join(tool_docs)

        core_mem = self._get_core_memory_text()
        core_mem_block = f"\n<core_memory>\n{core_mem}\n</core_memory>\n" if core_mem else ""

        system_prompt = (
            "You are Friday, an ultra-advanced, loyal, highly capable personal AI assistant.\n"
            "You operate on a 'Cloud-Brain, Local-Body' architecture:\n"
            "- Your reasoning and intelligence reside in the cloud (Gemini).\n"
            "- Your physical senses and hands reside locally on the user's Windows machine.\n"
            "The user is a 2nd-year B.Tech Electronics & Telecommunication Engineering (ENTC) student.\n"
            "Hardware constraints: Intel i5-12450H CPU, 16 GB RAM, RTX 3050 GPU (0% background ML GPU policy).\n"
            f"{core_mem_block}\n"
            "LOCAL TOOLS AVAILABLE IN YOUR BODY:\n"
            f"{tools_str}\n\n"
            "TOOL CALLING FORMAT:\n"
            "When you need to inspect files, write fixes, run bash commands, or save to memory, output an action block:\n"
            "```action\n"
            "{\n"
            '  "tool": "<tool_name>",\n'
            '  "parameters": { ... }\n'
            "}\n"
            "```\n"
            "You will receive the local execution output in a subsequent message as '[Observation for <tool_name>]: ...'.\n"
            "You can execute multiple steps in sequence (inspect -> patch -> test -> reflect).\n"
            "Always explain your engineering rationale clearly."
        )

        try:
            if hasattr(self.llm, "set_system_instruction"):
                self.llm.set_system_instruction(system_prompt)
        except Exception:
            pass

    def register_tool(self, tool: BaseTool) -> None:
        """Register a tool with Friday's body."""
        self.tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Retrieve a registered tool by name."""
        return self.tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        """List metadata for all registered tools."""
        return [tool.to_dict() for tool in self.tools.values()]

    def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        action_description: Optional[str] = None,
    ) -> Any:
        """Execute a tool through the tiered permission gate.

        Args:
            tool_name: Name of registered tool.
            parameters: Arguments to pass to tool.execute().
            action_description: Human-readable summary for security prompt.

        Returns:
            Tool execution result.

        Raises:
            KeyError: Tool not registered.
            PermissionError: User declined irreversible action.
        """
        tool = self.get_tool(tool_name)
        if not tool:
            raise KeyError(f"Tool '{tool_name}' is not registered.")

        desc = action_description or f"Execute tool '{tool_name}' with parameters {parameters}"
        authorized = self.gate.check_and_authorize(
            tool_name=tool_name,
            tier=tool.tier,
            description=desc,
            params=parameters,
        )

        if not authorized:
            self.gate.log_execution(
                tool_name=tool_name,
                tier=tool.tier,
                params=parameters,
                approved=False,
                error="Action denied by permission gate.",
            )
            raise PermissionError(f"Action '{tool_name}' was declined by user.")

        try:
            result = tool.execute(**parameters)
            self.gate.log_execution(
                tool_name=tool_name,
                tier=tool.tier,
                params=parameters,
                approved=True,
                result=result,
            )
            return result
        except Exception as exc:
            self.gate.log_execution(
                tool_name=tool_name,
                tier=tool.tier,
                params=parameters,
                approved=True,
                error=str(exc),
            )
            raise

    def process(self, user_input: str, max_iterations: int = 5) -> str:
        """Process user input through the Cloud Brain with agentic tool loop.

        Args:
            user_input: Message from user.
            max_iterations: Maximum tool call iterations before concluding.

        Returns:
            Friday's final synthesized response.
        """
        self._update_system_instructions()

        # 1. Check for quick manual memory intent (e.g., "remember: Title - Content")
        remember_match = re.match(
            r"^remember(?:\s*that|\s*:)\s*(.+)$", user_input.strip(), re.IGNORECASE
        )
        if remember_match:
            raw_memory = remember_match.group(1).strip()
            if " | " in raw_memory:
                title, content = raw_memory.split(" | ", 1)
            elif " - " in raw_memory:
                title, content = raw_memory.split(" - ", 1)
            else:
                words = raw_memory.split()
                title = " ".join(words[:4]).title()
                content = raw_memory

            res = self.execute_tool(
                "remember",
                {"title": title, "content": content, "category": "user_memory"},
                action_description=f"Save note '{title}' into Obsidian vault",
            )
            return (
                f"[Saved to Obsidian Vault]\n"
                f"- Note: {res['title']}\n"
                f"- Path: {res['file_path']}\n"
                f"Memory has been indexed into your local vector database and knowledge graph."
            )

        if not self.llm.is_configured():
            return (
                "[!] [Friday Configuration Required]\n"
                "I am ready, but my cloud brain (Gemini API) is not connected yet.\n"
                "Please add your GEMINI_API_KEY to the .env file in the project root:\n\n"
                "    GEMINI_API_KEY=your_actual_key_here\n\n"
                "You can get a free key from Google AI Studio: https://aistudio.google.com/"
            )

        # 2. Context Builder (CPU Vector RAG + GraphRAG)
        context_prompt = user_input
        try:
            recall_res = self.memory.recall(query=user_input, top_k=2, max_hops=2)
            formatted_ctx = recall_res.get("formatted_context", "")
            if formatted_ctx:
                context_prompt = (
                    f"Background Memory from Obsidian Vault:\n"
                    f"{formatted_ctx}\n\n"
                    f"User Inquiry: {user_input}"
                )
        except Exception:
            context_prompt = user_input

        # 3. Agentic Execution Loop
        current_input = context_prompt
        iteration = 0
        final_response = ""

        while iteration < max_iterations:
            iteration += 1
            try:
                model_reply = self.llm.chat(current_input)
            except Exception as exc:
                return f"[X] [Brain Error]: {str(exc)}"

            # Parse for tool action blocks
            action_matches = ACTION_PATTERN.findall(model_reply)
            if not action_matches:
                final_response = model_reply
                break

            observations: List[str] = []
            for match in action_matches:
                try:
                    action_data = json.loads(match.strip())
                    tool_name = action_data.get("tool", "")
                    params = action_data.get("parameters", {})

                    try:
                        tool_result = self.execute_tool(tool_name, params)
                        obs_str = json.dumps(tool_result, indent=2) if isinstance(tool_result, (dict, list)) else str(tool_result)
                        observations.append(f"[Observation for {tool_name}]:\n{obs_str}")
                    except PermissionError as perm_err:
                        observations.append(f"[Security Gate]: User declined permission for action '{tool_name}'. {str(perm_err)}")
                    except Exception as tool_err:
                        observations.append(f"[Tool Execution Error in {tool_name}]: {str(tool_err)}")

                except json.JSONDecodeError as json_err:
                    observations.append(f"[Action Parse Error]: Invalid JSON in action block: {str(json_err)}")

            # Send observations back to Cloud Brain
            current_input = "\n\n".join(observations)
            final_response = model_reply

        return final_response

    def handle_audio(self, audio_bytes: bytes, max_iterations: int = 5) -> str:
        """Process spoken user audio through Gemini multimodal speech-to-speech loop.

        Args:
            audio_bytes: 16kHz mono WAV audio bytes recorded from microphone.
            max_iterations: Maximum tool call iterations.

        Returns:
            Friday's synthesized text response (concise, spoken format).
        """
        if not self.llm.is_configured():
            return (
                "[!] [Friday Configuration Required]\n"
                "I am ready, but my cloud brain (Gemini API) is not connected yet.\n"
                "Please add your GEMINI_API_KEY to the .env file in the project root."
            )

        instruction = (
            "Listen to the user's spoken audio request carefully.\n"
            "If the user asks you to remember, save, inspect, code, or execute any tool, output an action block:\n"
            "```action\n"
            "{\n"
            '  "tool": "<tool_name>",\n'
            '  "parameters": { ... }\n'
            "}\n"
            "```\n"
            "Otherwise, formulate a direct, natural, concise conversational spoken reply suited for Text-To-Speech output."
        )

        try:
            model_reply = self.llm.generate_with_audio(instruction, audio_bytes)
        except Exception as exc:
            return f"I ran into an issue processing your audio: {exc}"

        # Check if the model requested any tool executions
        action_matches = ACTION_PATTERN.findall(model_reply)
        if not action_matches:
            # Check for direct manual remember intent in audio transcript
            remember_match = re.match(
                r"^remember(?:\s*that|\s*:)\s*(.+)$", model_reply.strip(), re.IGNORECASE
            )
            if remember_match:
                raw_memory = remember_match.group(1).strip()
                words = raw_memory.split()
                title = " ".join(words[:4]).title()
                res = self.execute_tool(
                    "remember",
                    {"title": title, "content": raw_memory, "category": "spoken_memory"},
                )
                return f"I've saved {title} to your Obsidian vault."
            return model_reply

        # Execute actions if produced
        observations: List[str] = []
        for match in action_matches:
            try:
                action_data = json.loads(match.strip())
                tool_name = action_data.get("tool", "")
                params = action_data.get("parameters", {})

                try:
                    tool_result = self.execute_tool(tool_name, params)
                    obs_str = json.dumps(tool_result, indent=2) if isinstance(tool_result, (dict, list)) else str(tool_result)
                    observations.append(f"[Observation for {tool_name}]:\n{obs_str}")
                except PermissionError as perm_err:
                    observations.append(f"[Security Gate]: User declined permission for action '{tool_name}'. {str(perm_err)}")
                except Exception as tool_err:
                    observations.append(f"[Tool Execution Error in {tool_name}]: {str(tool_err)}")
            except json.JSONDecodeError as json_err:
                observations.append(f"[Action Parse Error]: Invalid JSON in action block: {str(json_err)}")

        followup_prompt = (
            f"Here are the local tool execution results:\n"
            f"{chr(10).join(observations)}\n\n"
            f"Provide a natural, concise spoken confirmation aloud to the user."
        )
        try:
            final_reply = self.llm.chat(followup_prompt)
            return final_reply
        except Exception:
            return model_reply

    def reset_conversation(self) -> None:
        """Reset the conversation context."""
        self.llm.reset_chat()
