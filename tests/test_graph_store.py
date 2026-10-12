"""Unit tests for NetworkX GraphStore."""

import pytest
from pathlib import Path
from friday.memory.graph_store import GraphStore
from friday.memory.models import MemoryNode


def test_graph_wiring_and_2_hop_neighborhood(tmp_path: Path):
    cache_file = tmp_path / "test_graph.json"
    graph_store = GraphStore(persistence_file=str(cache_file))

    # Node A: Signals links to Node B (Fourier) and Node C (Sampling)
    node_a = MemoryNode(
        id="signals",
        title="Signals and Systems",
        content="Intro to signals. See [[Fourier Analysis]] and [[Sampling Theorem]].",
        links=["Fourier Analysis", "Sampling Theorem"],
    )
    # Node B: Fourier Analysis links to Node D (Laplace)
    node_b = MemoryNode(
        id="fourier-analysis",
        title="Fourier Analysis",
        content="Frequency analysis. Connects to [[Laplace Transform]].",
        links=["Laplace Transform"],
    )
    # Node D: Laplace Transform links to Node E (Z Transform)
    node_d = MemoryNode(
        id="laplace-transform",
        title="Laplace Transform",
        content="Continuous S-domain. See [[Z Transform]].",
        links=["Z Transform"],
    )

    graph_store.add_memory_node(node_a)
    graph_store.add_memory_node(node_b)
    graph_store.add_memory_node(node_d)

    # 1. Check stats
    stats = graph_store.stats()
    assert stats["total_nodes"] >= 4
    assert stats["total_edges"] >= 3

    # 2. Traverse neighborhood from "Signals and Systems" with max_hops=2
    # 1-hop: Fourier Analysis, Sampling Theorem
    # 2-hop: Laplace Transform
    # 3-hop: Z Transform (should NOT be included when max_hops=2)
    neighbors = graph_store.traverse_neighborhood(
        seed_node_ids=["signals"],
        max_hops=2,
    )
    neighbor_titles = [n["title"] for n in neighbors]
    neighbor_hops = {n["title"]: n["distance_hops"] for n in neighbors}

    assert "Fourier Analysis" in neighbor_titles
    assert neighbor_hops["Fourier Analysis"] == 1

    assert "Sampling Theorem" in neighbor_titles
    assert neighbor_hops["Sampling Theorem"] == 1

    assert "Laplace Transform" in neighbor_titles
    assert neighbor_hops["Laplace Transform"] == 2

    # Z Transform is 3 hops away from Signals, so it shouldn't be included
    assert "Z Transform" not in neighbor_titles


def test_graph_persistence_roundtrip(tmp_path: Path):
    cache_file = tmp_path / "test_graph.json"
    graph_store = GraphStore(persistence_file=str(cache_file))

    node = MemoryNode(
        id="control-systems",
        title="Control Systems",
        content="Feedback loops [[State Space]].",
        links=["State Space"],
    )
    graph_store.add_memory_node(node)
    graph_store.save()

    assert cache_file.exists()

    # Reload into fresh instance
    reloaded = GraphStore(persistence_file=str(cache_file))
    assert reloaded.graph.has_node("control-systems")
    assert reloaded.graph.has_node("state-space")
