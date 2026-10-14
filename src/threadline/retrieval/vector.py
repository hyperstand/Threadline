"""M4 replaceable vector adapter and local embedding helpers."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, Sequence


@dataclass
class VectorHit:
    chunk_id: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorAdapter(Protocol):
    def upsert(self, chunk_id: str, embedding: list[float], metadata: Optional[dict[str, Any]] = None) -> None: ...
    def search(self, query_vector: list[float], limit: int = 10) -> list[VectorHit]: ...
    def delete_document(self, document_id: str) -> None: ...


class EmbeddingProvider(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class InMemoryVectorAdapter:
    def __init__(self) -> None:
        self._vectors: dict[str, list[float]] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    def upsert(self, chunk_id: str, embedding: list[float], metadata: Optional[dict[str, Any]] = None) -> None:
        if not embedding:
            return
        self._vectors[chunk_id] = _normalize(embedding)
        self._metadata[chunk_id] = dict(metadata or {})

    def upsert_many(self, items):
        for chunk_id, embedding, metadata in items:
            self.upsert(chunk_id, embedding, metadata)

    def search(self, query_vector: list[float], limit: int = 10) -> list[VectorHit]:
        if not self._vectors:
            return []
        q = _normalize(query_vector)
        scored = []
        for chunk_id, vector in self._vectors.items():
            score = _cosine(q, vector)
            scored.append(VectorHit(chunk_id=chunk_id, score=score, metadata=self._metadata.get(chunk_id, {})))
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:max(1, limit)]

    def delete_document(self, document_id: str) -> None:
        to_delete = [cid for cid, md in self._metadata.items() if md.get("document_id") == document_id]
        for cid in to_delete:
            self._vectors.pop(cid, None)
            self._metadata.pop(cid, None)

    def count(self) -> int:
        return len(self._vectors)


class HashingEmbeddingProvider:
    """Deterministic local fallback. Not a real semantic model, but useful for tests/dev."""

    DIM = 64

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.DIM
        for token in (text or "").lower().split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.DIM
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[idx] += sign
        return vector


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0:
        return list(vector)
    return [x / norm for x in vector]


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def create_vector_adapter(settings: Any = None) -> Optional[InMemoryVectorAdapter]:
    # Placeholder for backend selection; default to in-memory for MVP when enabled.
    backend = getattr(settings, "vector_backend", "memory") if settings is not None else "memory"
    if backend in (None, "", "disabled"):
        return None
    return InMemoryVectorAdapter()


def create_embedding_provider(settings: Any = None):
    backend = getattr(settings, "embedding_backend", "hash") if settings is not None else "hash"
    if backend == "hash":
        return HashingEmbeddingProvider()
    # Actual provider integrations arrive with LangChain model interfaces (M5).
    return None
