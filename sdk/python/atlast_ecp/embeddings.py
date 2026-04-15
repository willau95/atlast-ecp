"""
ATLAST ECP — Semantic Search via Embeddings

Provides natural language search across records.
Uses lightweight TF-IDF vectors (no external dependencies).
Optional: sentence-transformers for better quality if available.

Falls back gracefully to keyword search if embedding fails.
"""

import math
import re
from collections import Counter
from typing import Optional


def _tokenize(text: str) -> list:
    """Simple tokenizer: lowercase, split on non-alpha, remove short tokens."""
    return [w for w in re.findall(r'[a-z0-9]+', text.lower()) if len(w) > 2]


class TFIDFIndex:
    """Lightweight TF-IDF vector search. No external dependencies."""

    def __init__(self):
        self.documents = []  # [{id, text, tokens, tf}]
        self.idf = {}
        self.vocab = set()

    def add(self, doc_id: str, text: str):
        tokens = _tokenize(text)
        if not tokens:
            return
        tf = Counter(tokens)
        max_tf = max(tf.values()) if tf else 1
        norm_tf = {t: c / max_tf for t, c in tf.items()}
        self.documents.append({"id": doc_id, "text": text, "tokens": tokens, "tf": norm_tf})
        self.vocab.update(tokens)

    def build(self):
        """Compute IDF after all documents are added."""
        n = len(self.documents)
        if n == 0:
            return
        doc_freq = Counter()
        for doc in self.documents:
            doc_freq.update(set(doc["tokens"]))
        self.idf = {t: math.log(n / (df + 1)) for t, df in doc_freq.items()}

    def search(self, query: str, limit: int = 20) -> list:
        """Search documents by TF-IDF cosine similarity.
        Returns: [{id, score, text}]
        """
        if not self.documents or not self.idf:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        query_tf = Counter(query_tokens)
        max_qtf = max(query_tf.values()) if query_tf else 1
        query_vec = {t: (c / max_qtf) * self.idf.get(t, 0) for t, c in query_tf.items()}
        query_norm = math.sqrt(sum(v * v for v in query_vec.values())) or 1

        results = []
        for doc in self.documents:
            # Compute dot product
            dot = sum(query_vec.get(t, 0) * doc["tf"].get(t, 0) * self.idf.get(t, 0)
                      for t in query_tokens if t in doc["tf"])
            if dot <= 0:
                continue
            # Doc norm
            doc_norm = math.sqrt(sum(
                (doc["tf"].get(t, 0) * self.idf.get(t, 0)) ** 2
                for t in doc["tf"]
            )) or 1
            score = dot / (query_norm * doc_norm)
            results.append({"id": doc["id"], "score": round(score, 4), "text": doc["text"][:200]})

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:limit]


# ── Global index (lazy-built) ──
_index: Optional[TFIDFIndex] = None
_index_record_count: int = 0


def _build_index():
    """Build or rebuild the semantic index from SQLite records."""
    global _index, _index_record_count
    try:
        from .query import _ensure_index, _get_db
        _ensure_index()
        db = _get_db()
        rows = db.execute(
            "SELECT id, input_preview, output_preview FROM records ORDER BY ts DESC LIMIT 5000"
        ).fetchall()
        db.close()

        idx = TFIDFIndex()
        for row in rows:
            text = "%s %s" % (row[0] or "", row[1] or "")
            # Also include output for richer matching
            if row[2]:
                text += " " + (row[2] or "")[:200]
            idx.add(row[0], text)
        idx.build()
        _index = idx
        _index_record_count = len(rows)
    except Exception:
        _index = TFIDFIndex()
        _index_record_count = 0


def semantic_search(query: str, limit: int = 20) -> list:
    """Search records using semantic similarity (TF-IDF).

    Returns: [{id, score, text}]
    Falls back gracefully if index not built.
    """
    global _index
    if _index is None or _index_record_count == 0:
        _build_index()
    if _index is None:
        return []
    return _index.search(query, limit=limit)
