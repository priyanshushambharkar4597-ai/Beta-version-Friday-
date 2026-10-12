"""Data models for Friday's Obsidian-Power Memory Engine."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


WIKILINK_PATTERN = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


@dataclass
class MemoryNode:
    """Represents a discrete memory unit synced with an Obsidian Markdown file."""
    id: str
    title: str
    content: str
    category: str = "general"
    tags: List[str] = field(default_factory=list)
    links: List[str] = field(default_factory=list)
    file_path: Optional[str] = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: Dict[str, Any] = field(default_factory=dict)

    def extract_wikilinks(self) -> List[str]:
        """Extract all Obsidian-style [[WikiLinks]] from the markdown body."""
        found = WIKILINK_PATTERN.findall(self.content)
        # Merge with frontmatter links and deduplicate
        all_links = set(self.links)
        for link in found:
            all_links.add(link.strip())
        return sorted(list(all_links))

    def to_frontmatter_dict(self) -> Dict[str, Any]:
        """Produce dictionary suitable for YAML frontmatter."""
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "tags": self.tags,
            "links": self.links,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_obsidian_markdown(self) -> str:
        """Format node as Obsidian-compatible markdown with YAML frontmatter."""
        import yaml

        frontmatter = yaml.dump(
            self.to_frontmatter_dict(), sort_keys=False, default_flow_style=False
        ).strip()

        return f"---\n{frontmatter}\n---\n\n# {self.title}\n\n{self.content}\n"
