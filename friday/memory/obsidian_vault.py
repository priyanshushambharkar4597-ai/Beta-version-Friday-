"""Obsidian Vault Syncer - Handles disk I/O for Obsidian-compatible Markdown files."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
import yaml

from friday.memory.models import MemoryNode


def slugify(text: str) -> str:
    """Convert title to a Windows-safe filename."""
    # Remove characters invalid in Windows paths: < > : " / \ | ? *
    cleaned = re.sub(r'[<>:"/\\|?*]', "", text)
    cleaned = re.sub(r"[\s_]+", "-", cleaned).strip("-")
    return cleaned[:100] or "untitled"


class ObsidianVault:
    """Manages the physical Obsidian markdown vault on disk."""

    def __init__(self, vault_dir: Optional[str] = None) -> None:
        """Initialize Obsidian Vault.

        Args:
            vault_dir: Absolute or relative path to vault folder. Defaults to ./vault.
        """
        if vault_dir is None:
            self.vault_dir = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "vault")))
        else:
            self.vault_dir = Path(os.path.abspath(vault_dir))

        self.vault_dir.mkdir(parents=True, exist_ok=True)

    def get_path_for_title(self, title: str) -> Path:
        """Get file path for given note title."""
        slug = slugify(title)
        return self.vault_dir / f"{slug}.md"

    def save_node(self, node: MemoryNode) -> str:
        """Save a MemoryNode as an Obsidian-compatible markdown file.

        Args:
            node: The MemoryNode to save.

        Returns:
            Absolute file path of the saved markdown note.
        """
        file_path = self.get_path_for_title(node.title)
        node.file_path = str(file_path)
        node.updated_at = datetime.now(timezone.utc).isoformat()

        content = node.to_obsidian_markdown()
        file_path.write_text(content, encoding="utf-8")
        return str(file_path)

    def load_node_from_file(self, file_path: Path) -> Optional[MemoryNode]:
        """Read and parse an Obsidian markdown file into a MemoryNode."""
        if not file_path.exists() or not file_path.suffix == ".md":
            return None

        raw = file_path.read_text(encoding="utf-8")
        if not raw.startswith("---"):
            # Plain markdown without frontmatter
            title = file_path.stem.replace("-", " ").title()
            return MemoryNode(
                id=file_path.stem,
                title=title,
                content=raw.strip(),
                file_path=str(file_path),
            )

        parts = raw.split("---", 2)
        if len(parts) < 3:
            return None

        yaml_content = parts[1]
        body = parts[2].strip()

        try:
            meta = yaml.safe_load(yaml_content) or {}
        except Exception:
            meta = {}

        # Strip heading if present at top of body
        lines = body.splitlines()
        if lines and lines[0].startswith("# "):
            body = "\n".join(lines[1:]).strip()

        node_id = meta.get("id", file_path.stem)
        title = meta.get("title", file_path.stem.replace("-", " ").title())
        category = meta.get("category", "general")
        tags = meta.get("tags", [])
        links = meta.get("links", [])
        created_at = meta.get("created_at", datetime.now(timezone.utc).isoformat())
        updated_at = meta.get("updated_at", datetime.now(timezone.utc).isoformat())

        return MemoryNode(
            id=str(node_id),
            title=title,
            content=body,
            category=category,
            tags=tags if isinstance(tags, list) else [str(tags)],
            links=links if isinstance(links, list) else [str(links)],
            file_path=str(file_path),
            created_at=str(created_at),
            updated_at=str(updated_at),
            metadata=meta,
        )

    def load_all_nodes(self) -> List[MemoryNode]:
        """Load all Obsidian markdown notes from the vault."""
        nodes: List[MemoryNode] = []
        for p in self.vault_dir.glob("*.md"):
            node = self.load_node_from_file(p)
            if node:
                nodes.append(node)
        return nodes

    def delete_node(self, title: str) -> bool:
        """Delete an Obsidian note by title."""
        target = self.get_path_for_title(title)
        if target.exists():
            target.unlink()
            return True
        return False
