"""Integration tests for HybridMemoryEngine and FridayAgent integration."""

import os
from pathlib import Path
import pytest
from unittest.mock import MagicMock

from friday.agent import FridayAgent
from friday.llm.gemini_provider import GeminiProvider
from friday.memory.retriever import HybridMemoryEngine


def test_hybrid_memory_engine_remember_and_recall(tmp_path: Path):
    vault_dir = tmp_path / "vault"
    db_file = tmp_path / "vectors.db"
    graph_file = tmp_path / "graph.json"

    engine = HybridMemoryEngine(
        vault_dir=str(vault_dir),
        db_path=str(db_file),
        graph_cache=str(graph_file),
    )

    # 1. Remember note A
    node_a = engine.remember(
        title="Microcontrollers and Embedded Systems",
        content="Overview of ARM Cortex-M architecture. Connects to [[RTOS Fundamentals]] and [[SPI Protocol]].",
        category="entc_hardware",
        tags=["embedded", "arm", "microcontroller"],
        links=["RTOS Fundamentals"],
    )

    # Acceptance test: physically saved as an Obsidian .md file
    md_file = Path(node_a.file_path)
    assert md_file.exists()
    assert md_file.name == "Microcontrollers-and-Embedded-Systems.md"
    assert "ARM Cortex-M" in md_file.read_text(encoding="utf-8")

    # 2. Remember note B (1 hop away)
    engine.remember(
        title="RTOS Fundamentals",
        content="FreeRTOS scheduling, semaphores, and queues. Links to [[Task Synchronization]].",
        category="embedded",
        tags=["rtos", "freertos"],
        links=["Task Synchronization"],
    )

    # 3. Remember note C (2 hops away)
    engine.remember(
        title="Task Synchronization",
        content="Mutexes and priority inversion mechanisms.",
        category="embedded",
        tags=["rtos", "concurrency"],
    )

    # 4. Perform Hybrid Recall
    recall_res = engine.recall(query="ARM Cortex microcontroller architecture", top_k=1, max_hops=2)

    # Check direct vector match
    assert len(recall_res["direct_matches"]) >= 1
    top_hit = recall_res["direct_matches"][0]
    assert top_hit["title"] == "Microcontrollers and Embedded Systems"
    assert top_hit["score"] > 0.0

    # Check 2-hop graph neighborhood expansion
    graph_ctx = recall_res["graph_context"]
    ctx_titles = [g["title"] for g in graph_ctx]

    # RTOS Fundamentals is 1 hop away
    assert "RTOS Fundamentals" in ctx_titles
    # Task Synchronization is 2 hops away via RTOS Fundamentals
    assert "Task Synchronization" in ctx_titles

    # Check formatted prompt context bundle
    formatted = recall_res["formatted_context"]
    assert "Obsidian Memory Engine Context" in formatted
    assert "Microcontrollers and Embedded Systems" in formatted
    assert "RTOS Fundamentals" in formatted


def test_agent_remember_intent(tmp_path: Path):
    vault_dir = tmp_path / "vault"
    db_file = tmp_path / "vectors.db"
    graph_file = tmp_path / "graph.json"

    engine = HybridMemoryEngine(
        vault_dir=str(vault_dir),
        db_path=str(db_file),
        graph_cache=str(graph_file),
    )

    mock_llm = MagicMock(spec=GeminiProvider)
    mock_llm.is_configured.return_value = False

    agent = FridayAgent(gemini_provider=mock_llm, memory_engine=engine)

    # Send remember instruction
    response = agent.process("remember: Antenna Theory | Half-wave dipole radiation patterns [[Electromagnetics]]")

    assert "Saved to Obsidian Vault" in response
    assert "Antenna Theory" in response

    # Check file exists on disk
    vault_files = list(vault_dir.glob("*.md"))
    assert len(vault_files) == 1
    assert "Antenna-Theory.md" in vault_files[0].name
