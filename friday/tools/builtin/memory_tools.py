"""Memory tools for Friday's tool registry."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pathlib import Path
import re
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


class UpdateCoreMemoryTool(BaseTool):
    """Tool to update sections within Friday's pinned core memory note (_core_memory.md)."""

    name = "update_core_memory"
    description = (
        "Update or append a section in Friday's pinned core memory note (_core_memory.md). "
        "Allows updating user persona, active projects, and persistent directives."
    )
    tier = PermissionTier.REVERSIBLE

    def __init__(
        self,
        memory_engine: Optional[HybridMemoryEngine] = None,
        vault_dir: Optional[str] = None,
    ) -> None:
        self.memory_engine = memory_engine
        if memory_engine and hasattr(memory_engine, "vault") and hasattr(memory_engine.vault, "vault_dir"):
            self.vault_dir = Path(memory_engine.vault.vault_dir)
        elif vault_dir:
            self.vault_dir = Path(vault_dir)
        else:
            self.vault_dir = Path("vault")

    def execute(self, section: str, content: str, **kwargs: Any) -> Dict[str, Any]:
        core_file = self.vault_dir / "_core_memory.md"
        self.vault_dir.mkdir(parents=True, exist_ok=True)

        initial_template = (
            "---\n"
            "type: core_memory\n"
            "updated: auto\n"
            "---\n"
            "# Core Memory\n"
        )
        if not core_file.exists():
            text = initial_template
        else:
            text = core_file.read_text(encoding="utf-8")

        clean_section = section.strip().lstrip("#").strip()
        pattern = re.compile(
            rf"(^##\s+{re.escape(clean_section)}\s*$.*?)(?=(^##\s+)|\Z)",
            re.DOTALL | re.MULTILINE | re.IGNORECASE,
        )

        if pattern.search(text):
            updated_text = pattern.sub(f"## {clean_section}\n{content.strip()}\n\n", text)
        else:
            if not text.endswith("\n"):
                text += "\n"
            updated_text = f"{text}\n## {clean_section}\n{content.strip()}\n"

        core_file.write_text(updated_text.strip() + "\n", encoding="utf-8")
        return {
            "status": "updated",
            "section": clean_section,
            "path": str(core_file),
            "content": content.strip(),
        }

