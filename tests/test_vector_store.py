"""Unit tests for SQLite + NumPy VectorStore."""

import pytest
import numpy as np
from pathlib import Path
from friday.memory.vector_store import VectorStore, _cpu_deterministic_embedding


def test_cpu_deterministic_embedding():
    v1 = _cpu_deterministic_embedding("Digital Signal Processing Fourier Transform")
    v2 = _cpu_deterministic_embedding("Digital Signal Processing Fourier Transform")
    v3 = _cpu_deterministic_embedding("Completely unrelated topic about cooking")

    assert isinstance(v1, np.ndarray)
    assert v1.shape == (768,)
    # Consistent
    assert np.allclose(v1, v2)
    # Normalized
    assert np.isclose(np.linalg.norm(v1), 1.0, atol=1e-5)

    # Cosine similarity with self is 1.0
    sim_self = float(np.dot(v1, v2))
    assert np.isclose(sim_self, 1.0, atol=1e-4)

    # Cosine similarity with unrelated text is lower
    sim_diff = float(np.dot(v1, v3))
    assert sim_diff < 0.8


def test_vector_store_crud_and_search(tmp_path: Path):
    db_file = tmp_path / "test_vectors.db"
    store = VectorStore(db_path=str(db_file), dimension=768)

    # Upsert test documents
    store.upsert(
        node_id="signals-1",
        text="Fourier Transform decomposes a signal into frequency components.",
        metadata={"title": "Fourier Transform", "category": "math"},
    )
    store.upsert(
        node_id="circuits-1",
        text="Kirchhoff's Current Law states total current entering a junction equals leaving.",
        metadata={"title": "Kirchhoff Laws", "category": "circuits"},
    )

    assert store.count() == 2

    # Query for frequency signals
    results = store.search(query="frequency components in signals", top_k=2)
    assert len(results) == 2
    top_id, top_score, top_text, top_meta = results[0]
    assert top_id == "signals-1"
    assert top_meta["title"] == "Fourier Transform"
    assert top_score > 0.0

    # Delete
    deleted = store.delete("signals-1")
    assert deleted is True
    assert store.count() == 1
