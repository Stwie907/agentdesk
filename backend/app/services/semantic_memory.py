"""Cosine ranking over scoped rows; previews read cache and Runtime can populate it."""

from dataclasses import dataclass
import math

from app.models.memory import Memory
from app.models.user_memory import UserMemory
from app.services.memory_embeddings import (
    EmbeddingSettings, MOCK_QUERIES, SemanticMemoryUnavailable, embed_texts,
)
from app.services.memory_vector_cache import cached_embeddings


@dataclass(frozen=True)
class SemanticMatch:
    memory: Memory | UserMemory
    similarity: float


def rank_semantic_rows(rows: list[Memory | UserMemory], query: str, settings: EmbeddingSettings,
                       limit: int = 5, min_similarity: float | None = None, *, db=None,
                       populate_cache: bool = False, on_cache=None) -> list[SemanticMatch]:
    if not rows or limit <= 0 or not query.strip():
        return []
    if settings.provider == "mock" and query.strip() not in MOCK_QUERIES:
        raise SemanticMemoryUnavailable("Mock semantic search uses fixed fixtures. Try 'Keep it brief.' or select Keyword search.")
    minimum = settings.memory.min_similarity if min_similarity is None else min_similarity
    if not math.isfinite(minimum) or not 0 <= minimum <= 1:
        raise SemanticMemoryUnavailable("Minimum cosine similarity must be between 0 and 1.")
    if db is not None and settings.memory.cache_enabled:
        vectors, stats = cached_embeddings(db, rows, query.strip(), settings, embed_texts, populate=populate_cache)
    else:
        vectors = embed_texts([query.strip(), *(row.content for row in rows)], settings)
        stats = {"version": 1, "status": "disabled", "documents": len(rows), "hits": 0,
                 "misses": len(rows), "written": 0, "provider": settings.provider, "model": settings.model}
    if len(vectors) != len(rows) + 1 or len({len(vector) for vector in vectors}) != 1:
        raise SemanticMemoryUnavailable("Embedding vectors do not match the scoped memory rows.")
    matches = []
    for memory, vector in zip(rows, vectors[1:]):
        similarity = round(max(-1.0, min(1.0, math.fsum(a * b for a, b in zip(vectors[0], vector)))), 6)
        if similarity > 0 and similarity >= minimum:
            matches.append(SemanticMatch(memory, similarity))
    matches.sort(key=lambda match: (match.similarity, match.memory.id), reverse=True)
    if on_cache is not None:
        on_cache(stats)
    return matches[:limit]
