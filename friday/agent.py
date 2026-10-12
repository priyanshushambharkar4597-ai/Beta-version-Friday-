"""Friday Agent - Core Orchestrator for Friday."""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional

from friday.llm.gemini_provider import GeminiProvider
from friday.tools.base import BaseTool, PermissionGate, PermissionTier


class FridayAgent:
    """Core orchestrator managing the Cloud Brain and Local Body interactions."""

    def __init__(
        self,
        gemini_provider: Optional[GeminiProvider] = None,
        permission_gate: Optional[PermissionGate] = None,
    ) -> None:
        """Initialize the Friday Agent.

        Args:
            gemini_provider: Configured Gemini LLM client. If None, instantiates default.
            permission_gate: Tiered security permission gate. If None, instantiates default.
        """
        self.llm = gemini_provider or GeminiProvider()
        self.gate = permission_gate or PermissionGate()
        self.tools: Dict[str, BaseTool] = {}

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
        """Process user input through the Cloud Brain (Gemini).

        Args:
            user_input: Message from user.

        Returns:
            Friday's response string.
        """
        if not self.llm.is_configured():
            return (
                "[!] [Friday Configuration Required]\n"
                "I am ready, but my cloud brain (Gemini API) is not connected yet.\n"
                "Please add your GEMINI_API_KEY to the .env file in the project root:\n\n"
                "    GEMINI_API_KEY=your_actual_key_here\n\n"
                "You can get a free key from Google AI Studio: https://aistudio.google.com/"
            )

        try:
            response = self.llm.chat(user_input)
            return response
        except Exception as exc:
            return f"[X] [Brain Error]: {str(exc)}"

    def reset_conversation(self) -> None:
        """Reset the conversation context."""
        self.llm.reset_chat()
