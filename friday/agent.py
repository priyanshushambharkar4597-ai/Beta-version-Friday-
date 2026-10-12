"""Friday Agent - Core Orchestrator for Friday."""

from __future__ import annotations

import os
import re
from typing import Any, Callable, Dict, List, Optional

from friday.llm.gemini_provider import GeminiProvider
from friday.memory.retriever import HybridMemoryEngine
from friday.tools.base import BaseTool, PermissionGate, PermissionTier
from friday.tools.builtin.memory_tools import RecallTool, RememberTool


class FridayAgent:
    """Core orchestrator managing the Cloud Brain and Local Body interactions."""

    def __init__(
        self,
        gemini_provider: Optional[GeminiProvider] = None,
        permission_gate: Optional[PermissionGate] = None,
        memory_engine: Optional[HybridMemoryEngine] = None,
    ) -> None:
        """Initialize the Friday Agent.

        Args:
            gemini_provider: Configured Gemini LLM client. If None, instantiates default.
            permission_gate: Tiered security permission gate. If None, instantiates default.
            memory_engine: Hybrid Obsidian vector + GraphRAG engine.
        """
        self.llm = gemini_provider or GeminiProvider()
        self.gate = permission_gate or PermissionGate()
        self.memory = memory_engine or HybridMemoryEngine()
        self.tools: Dict[str, BaseTool] = {}

        # Register built-in memory tools
        self.register_tool(RememberTool(self.memory))
        self.register_tool(RecallTool(self.memory))

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

    def process(self, user_input: str) -> str:
        """Process user input through the Cloud Brain (Gemini) with Obsidian GraphRAG.

        Args:
            user_input: Message from user.

        Returns:
            Friday's response string.
        """
        # 1. Check for quick memory intent (e.g., "remember: Title | Content" or "remember that ...")
        remember_match = re.match(
            r"^remember(?:\s*that|\s*:)\s*(.+)$", user_input.strip(), re.IGNORECASE
        )
        if remember_match:
            raw_memory = remember_match.group(1).strip()
            # If formatted as "Title | Content" or "Title: Content"
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
            # Silently degrade if memory search hits any error
            context_prompt = user_input

        # 3. Cloud Brain Reasoning
        try:
            response = self.llm.chat(context_prompt)
            return response
        except Exception as exc:
            return f"[X] [Brain Error]: {str(exc)}"

    def reset_conversation(self) -> None:
        """Reset the conversation context."""
        self.llm.reset_chat()
