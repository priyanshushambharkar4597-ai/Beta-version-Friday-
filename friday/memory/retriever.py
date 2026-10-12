"""Hybrid Retriever & Memory Manager - Integrates Obsidian, VectorStore, and GraphStore."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from friday.memory.graph_store import GraphStore
from friday.memory.models import MemoryNode
from friday.memory.obsidian_vault import ObsidianVault, slugify
from friday.memory.vector_store import VectorStore


class HybridMemoryEngine:
    """Orchestrates Obsidian Markdown vault, SQLite vector search, and NetworkX GraphRAG."""

    def __init__(
        self,
        vault_dir: Optional[str] = None,
        db_path: Optional[str] = None,
        graph_cache: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        """Initialize the hybrid memory engine.

        Args:
            vault_dir: Path to Obsidian vault. Defaults to ./vault.
            db_path: Path to SQLite vector DB. Defaults to ./vault/memory_vectors.db.
            graph_cache: Path to graph cache JSON. Defaults to ./vault/.graph_index.json.
            api_key: Google AI Studio API key.
        """
        self.vault = ObsidianVault(vault_dir=vault_dir)
        self.vector_store = VectorStore(db_path=db_path, api_key=api_key)
        self.graph_store = GraphStore(persistence_file=graph_cache)

        # Initial sync of vault contents
        self.sync()

    def sync(self) -> int:
        """Scan physical vault and synchronize both vector and graph indices."""
        nodes = self.vault.load_all_nodes()
        for node in nodes:
            # Re-index vectors
            self.vector_store.upsert(
                node_id=node.id,
                text=f"{node.title}\n{node.content}\nTags: {' '.join(node.tags)}",
                metadata=node.to_frontmatter_dict(),
            )
        self.graph_store.sync_vault(nodes)
        return len(nodes)

    def remember(
        self,
        title: str,
        content: str,
        category: str = "general",
        tags: Optional[List[str]] = None,
        links: Optional[List[str]] = None,
    ) -> MemoryNode:
        """Save a new memory physically as an Obsidian markdown file and index it.

        Args:
            title: Human-readable note title.
            content: Note body (supports markdown and [[wikilinks]]).
            category: Domain classification (e.g., 'coursework', 'coding', 'personal').
            tags: List of tags.
            links: List of linked note titles.

        Returns:
            The created and persisted MemoryNode.
        """
        node_id = slugify(title)
        node = MemoryNode(
            id=node_id,
            title=title,
            content=content,
            category=category,
            tags=tags or [],
            links=links or [],
        )

        # 1. Save physical Obsidian markdown file
        saved_path = self.vault.save_node(node)

        # 2. Index into SQLite Vector Store on CPU
        index_text = f"{title}\n{content}\nTags: {' '.join(node.tags)}"
        self.vector_store.upsert(
            node_id=node.id,
            text=index_text,
            metadata=node.to_frontmatter_dict(),
        )

        # 3. Add to Knowledge Graph and persist
        self.graph_store.add_memory_node(node)
        self.graph_store.save()

        return node

    def recall(
        self,
        query: str,
        top_k: int = 3,
        max_hops: int = 2,
    ) -> Dict[str, Any]:
        """Perform hybrid retrieval: Vector similarity + 2-hop Graph neighborhood expansion.

        Args:
            query: User search query or question.
            top_k: Number of direct vector matches.
            max_hops: Outward graph traversal depth (default 2).

        Returns:
            Dictionary containing:
                - direct_matches: List of top vector hits with similarity scores.
                - graph_context: List of neighboring nodes discovered via 1-hop and 2-hop links.
                - formatted_context: Clean string formatted for LLM prompt injection.
        """
        # Step 1: Semantic Vector Search on CPU
        vector_hits = self.vector_store.search(query=query, top_k=top_k)

        direct_matches: List[Dict[str, Any]] = []
        seed_ids: List[str] = []

        for v_id, score, text, meta in vector_hits:
            seed_ids.append(v_id)
            # Fetch latest node from vault
            title = meta.get("title", v_id)
            file_path = self.vault.get_path_for_title(title)
            node = self.vault.load_node_from_file(file_path)

            direct_matches.append({
                "id": v_id,
                "title": title,
                "score": round(score, 4),
                "category": meta.get("category", "general"),
                "tags": meta.get("tags", []),
                "content": node.content if node else text,
                "file_path": str(file_path) if file_path.exists() else None,
            })

        # Step 2: 2-Hop Knowledge Graph Expansion
        graph_neighbors = self.graph_store.traverse_neighborhood(
            seed_node_ids=seed_ids,
            max_hops=max_hops,
        )

        # Hydrate graph neighbors with full content from disk where available
        enriched_graph_context: List[Dict[str, Any]] = []
        for g in graph_neighbors:
            g_title = g.get("title", "")
            g_path = self.vault.get_path_for_title(g_title)
            g_node = self.vault.load_node_from_file(g_path) if g_path.exists() else None

            enriched_graph_context.append({
                "id": g.get("id"),
                "title": g_title,
                "distance_hops": g.get("distance_hops", 1),
                "category": g.get("category", "general"),
                "tags": g.get("tags", []),
                "content": g_node.content if g_node else "(Placeholder / Not yet created)",
                "file_path": str(g_path) if g_path.exists() else None,
            })

        # Step 3: Format Context Bundle for Gemini Orchestration
        formatted_context = self._format_context_bundle(direct_matches, enriched_graph_context)

        return {
            "query": query,
            "direct_matches": direct_matches,
            "graph_context": enriched_graph_context,
            "formatted_context": formatted_context,
        }

    def _format_context_bundle(
        self,
        direct: List[Dict[str, Any]],
        neighbors: List[Dict[str, Any]],
    ) -> str:
        """Format retrieved memories into a clean markdown block for LLM prompt."""
        if not direct and not neighbors:
            return ""

        sections: List[str] = ["### [Obsidian Memory Engine Context]"]

        if direct:
            sections.append("#### Direct Semantic Matches:")
            for d in direct:
                tags_str = " ".join([f"#{t}" for t in d['tags']]) if d['tags'] else ""
                sections.append(
                    f"- **{d['title']}** (Relevance: {d['score']}) {tags_str}\n"
                    f"  {d['content'].strip()}"
                )

        if neighbors:
            sections.append("\n#### Graph Connections (2-Hop Context):")
            for n in neighbors:
                hops = n['distance_hops']
                sections.append(
                    f"- **{n['title']}** ({hops}-hop connection)\n"
                    f"  {n['content'].strip()}"
                )

        return "\n".join(sections)

    def list_all_titles(self) -> List[str]:
        """List titles of all stored memories."""
        return [n.title for n in self.vault.load_all_nodes()]
