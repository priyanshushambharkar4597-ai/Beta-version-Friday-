"""Vector Store - SQLite + NumPy CPU-based semantic vector search engine."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import warnings
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# Suppress deprecation warnings for generative AI imports
warnings.filterwarnings("ignore", category=FutureWarning)


def _cpu_deterministic_embedding(text: str, dim: int = 768) -> np.ndarray:
    """Generate a deterministic CPU-only vector representation without GPU or heavy weights.

    Uses character n-grams and hashed bucket frequencies to simulate a dense
    semantic space for testing and offline fallback on Intel i5 CPUs.
    """
    vec = np.zeros(dim, dtype=np.float32)
    clean_text = text.lower().strip()
    words = clean_text.split()

    for word in words:
        # Word hash
        h = int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16)
        vec[h % dim] += 1.0

        # Character trigrams for morphological similarity
        for i in range(len(word) - 2):
            trigram = word[i : i + 3]
            th = int(hashlib.md5(trigram.encode("utf-8")).hexdigest(), 16)
            vec[th % dim] += 0.5

    # L2 normalize
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec


class VectorStore:
    """SQLite + NumPy vector database running entirely on CPU."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        dimension: int = 768,
        api_key: Optional[str] = None,
    ) -> None:
        """Initialize VectorStore.

        Args:
            db_path: Path to SQLite database file. Defaults to ./vault/memory_vectors.db.
            dimension: Dimensionality of embeddings (768 for text-embedding-004).
            api_key: Google AI Studio API key for cloud embeddings.
        """
        if db_path is None:
            default_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "vault")
            )
            os.makedirs(default_dir, exist_ok=True)
            self.db_path = os.path.join(default_dir, "memory_vectors.db")
        else:
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
            self.db_path = os.path.abspath(db_path)

        self.dimension = dimension
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self._init_db()

    def _init_db(self) -> None:
        """Create sqlite tables if not present."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_vectors (
                    id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    metadata TEXT,
                    vector BLOB NOT NULL,
                    dimension INTEGER NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    def embed_text(self, text: str) -> np.ndarray:
        """Generate embedding using Google Gemini API if online, or CPU fallback.

        Args:
            text: Input text string.

        Returns:
            1D NumPy array with shape (dimension,).
        """
        # If API key is present, try Google Cloud Brain free embedding
        if self.api_key:
            try:
                import google.generativeai as genai

                genai.configure(api_key=self.api_key)
                result = genai.embed_content(
                    model="models/text-embedding-004",
                    content=text,
                    task_type="retrieval_document",
                )
                raw_emb = result.get("embedding", [])
                if raw_emb:
                    arr = np.array(raw_emb, dtype=np.float32)
                    norm = np.linalg.norm(arr)
                    if norm > 0:
                        arr = arr / norm
                    return arr
            except Exception:
                # Silently fall back to deterministic CPU embedding
                pass

        # Zero-cost CPU fallback (Intel i5 CPU only, 0% GPU)
        return _cpu_deterministic_embedding(text, dim=self.dimension)

    def upsert(
        self,
        node_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        vector: Optional[np.ndarray] = None,
    ) -> None:
        """Insert or update a vector embedding.

        Args:
            node_id: Identifier matching MemoryNode id.
            text: Text content.
            metadata: Associated metadata dictionary.
            vector: Optional precomputed vector.
        """
        if vector is None:
            vector = self.embed_text(text)

        meta_json = json.dumps(metadata or {})
        vec_bytes = vector.astype(np.float32).tobytes()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO memory_vectors (id, text, metadata, vector, dimension)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    text = excluded.text,
                    metadata = excluded.metadata,
                    vector = excluded.vector,
                    dimension = excluded.dimension,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (node_id, text, meta_json, vec_bytes, len(vector)),
            )
            conn.commit()

    def search(
        self,
        query: str,
        top_k: int = 3,
        min_similarity: float = 0.0,
    ) -> List[Tuple[str, float, str, Dict[str, Any]]]:
        """Perform cosine similarity search on stored vectors.

        Args:
            query: Search query text.
            top_k: Number of nearest results to return.
            min_similarity: Minimum cosine similarity score threshold.

        Returns:
            List of tuples: (id, similarity_score, text, metadata).
        """
        query_vec = self.embed_text(query).astype(np.float32)
        q_norm = np.linalg.norm(query_vec)
        if q_norm == 0:
            return []
        query_vec = query_vec / q_norm

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, text, metadata, vector, dimension FROM memory_vectors")
            rows = cursor.fetchall()

        if not rows:
            return []

        ids: List[str] = []
        texts: List[str] = []
        metas: List[Dict[str, Any]] = []
        vectors: List[np.ndarray] = []

        for row in rows:
            r_id, r_text, r_meta, r_vec_blob, r_dim = row
            arr = np.frombuffer(r_vec_blob, dtype=np.float32)
            if len(arr) != len(query_vec):
                continue
            ids.append(r_id)
            texts.append(r_text)
            try:
                metas.append(json.loads(r_meta))
            except Exception:
                metas.append({})
            vectors.append(arr)

        if not vectors:
            return []

        # Vectorized cosine similarity on CPU
        matrix = np.vstack(vectors)  # Shape (N, dim)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        normed_matrix = matrix / norms

        scores = np.dot(normed_matrix, query_vec)  # Shape (N,)

        # Sort descending
        ranked_indices = np.argsort(scores)[::-1]

        results: List[Tuple[str, float, str, Dict[str, Any]]] = []
        for idx in ranked_indices[:top_k]:
            score = float(scores[idx])
            if score >= min_similarity:
                results.append((ids[idx], score, texts[idx], metas[idx]))

        return results

    def delete(self, node_id: str) -> bool:
        """Delete vector entry by node ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM memory_vectors WHERE id = ?", (node_id,))
            conn.commit()
            return cursor.rowcount > 0

    def count(self) -> int:
        """Count total stored vectors."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM memory_vectors")
            row = cursor.fetchone()
            return row[0] if row else 0
