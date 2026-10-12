"""Graph Store - NetworkX Knowledge Graph synchronizer for Obsidian vaults."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

from friday.memory.models import MemoryNode


class GraphStore:
    """Knowledge graph that mirrors and expands Obsidian wikilinks."""

    def __init__(self, persistence_file: Optional[str] = None) -> None:
        """Initialize GraphStore.

        Args:
            persistence_file: JSON path to serialize graph cache.
        """
        if persistence_file is None:
            vault_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "vault")
            )
            os.makedirs(vault_dir, exist_ok=True)
            self.persistence_file = os.path.join(vault_dir, ".graph_index.json")
        else:
            self.persistence_file = os.path.abspath(persistence_file)

        self.graph: nx.DiGraph = nx.DiGraph()
        self.load()

    def add_memory_node(self, node: MemoryNode) -> None:
        """Add a MemoryNode to the graph and wire its wikilinks.

        Args:
            node: MemoryNode to index.
        """
        norm_id = self._normalize_id(node.id or node.title)
        # Add or update primary node
        self.graph.add_node(
            norm_id,
            title=node.title,
            category=node.category,
            tags=node.tags,
            file_path=node.file_path,
            updated_at=node.updated_at,
        )

        # Wire all outgoing wikilinks
        outgoing = node.extract_wikilinks()
        for link_target in outgoing:
            target_id = self._normalize_id(link_target)
            if not self.graph.has_node(target_id):
                # Placeholder node until target note is created
                self.graph.add_node(
                    target_id,
                    title=link_target,
                    category="stub",
                    tags=[],
                    file_path=None,
                )
            self.graph.add_edge(norm_id, target_id, relation="links_to")

    def _normalize_id(self, title_or_id: str) -> str:
        """Normalize node title to consistent identifier."""
        import re
        cleaned = re.sub(r'[<>:"/\\|?*]', "", str(title_or_id))
        return re.sub(r"[\s_]+", "-", cleaned).strip("-").lower()

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Get node attributes by id."""
        if self.graph.has_node(node_id):
            return dict(self.graph.nodes[node_id])
        return None

    def traverse_neighborhood(
        self,
        seed_node_ids: List[str],
        max_hops: int = 2,
    ) -> List[Dict[str, Any]]:
        """Traverse graph outward up to max_hops from seed nodes.

        Args:
            seed_node_ids: Starting node IDs (e.g. from semantic vector search).
            max_hops: Maximum graph distance to explore (default 2-hops).

        Returns:
            List of neighbor dictionaries containing node metadata and hop distance.
        """
        visited: Dict[str, int] = {}
        queue: List[Tuple[str, int]] = []

        # Convert to undirected view for rich bidirectional contextual discovery
        undirected_view = self.graph.to_undirected()

        for s in seed_node_ids:
            norm_s = self._find_matching_node_id(s)
            if norm_s and undirected_view.has_node(norm_s):
                visited[norm_s] = 0
                queue.append((norm_s, 0))

        results: List[Dict[str, Any]] = []

        while queue:
            curr_id, hops = queue.pop(0)

            if hops > 0:  # Exclude seed nodes from the expansion set
                node_data = dict(self.graph.nodes[curr_id])
                node_data["id"] = curr_id
                node_data["distance_hops"] = hops
                results.append(node_data)

            if hops < max_hops:
                for neighbor in undirected_view.neighbors(curr_id):
                    if neighbor not in visited:
                        visited[neighbor] = hops + 1
                        queue.append((neighbor, hops + 1))

        return results

    def _find_matching_node_id(self, identifier: str) -> Optional[str]:
        """Look up node id either by direct match or case-insensitive title."""
        if self.graph.has_node(identifier):
            return identifier
        norm = self._normalize_id(identifier)
        if self.graph.has_node(norm):
            return norm
        for n, data in self.graph.nodes(data=True):
            if data.get("title", "").lower() == identifier.lower():
                return n
        return None

    def sync_vault(self, nodes: List[MemoryNode]) -> None:
        """Rebuild or sync the knowledge graph from an entire list of vault nodes."""
        self.graph.clear()
        for node in nodes:
            self.add_memory_node(node)
        self.save()

    def save(self) -> None:
        """Persist graph structure to JSON cache."""
        try:
            data = nx.node_link_data(self.graph)
            with open(self.persistence_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def load(self) -> None:
        """Load graph structure from JSON cache if present."""
        if os.path.exists(self.persistence_file):
            try:
                with open(self.persistence_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.graph = nx.node_link_graph(data, directed=True)
            except Exception:
                self.graph = nx.DiGraph()

    def stats(self) -> Dict[str, int]:
        """Graph metrics."""
        return {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
        }
