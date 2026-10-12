"""Memory tools for Friday's tool registry."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from friday.memory.retriever import HybridMemoryEngine
from friday.tools.base import BaseTool, PermissionTier


class RememberTool(BaseTool):
    """Tool to save memories into Friday's Obsidian vault and knowledge graph."""

    name = "remember"
    description = (
        "Save a note, fact, or code snippet into Friday's physical Obsidian markdown "
        "vault, embedding it in the vector store and linking it in the knowledge graph."
    )
    tier = PermissionTier.REVERSIBLE

    def __init__(self, memory_engine: HybridMemoryEngine) -> None:
        self.memory_engine = memory_engine

    def execute(
        self,
        title: str,
        content: str,
        category: str = "general",
        tags: Optional[List[str]] = None,
        links: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        node = self.memory_engine.remember(
            title=title,
            content=content,
            category=category,
            tags=tags,
            links=links,
        )
        return {
            "status": "saved",
            "id": node.id,
            "title": node.title,
            "file_path": node.file_path,
            "tags": node.tags,
            "links": node.links,
        }


class RecallTool(BaseTool):
    """Tool to retrieve memories using hybrid vector search + 2-hop graph expansion."""

    name = "recall"
    description = (
        "Search Friday's Obsidian vault using semantic vector similarity and 2-hop "
        "knowledge graph expansion to retrieve relevant notes and related concepts."
    )
    tier = PermissionTier.READ

    def __init__(self, memory_engine: HybridMemoryEngine) -> None:
        self.memory_engine = memory_engine

    def execute(
        self,
        query: str,
        top_k: int = 3,
        max_hops: int = 2,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        return self.memory_engine.recall(
            query=query,
            top_k=top_k,
            max_hops=max_hops,
        )
