"""Optional semantic memory settings; keyword retrieval remains the default."""

from dataclasses import dataclass
import math
import os


MEMORY_ENVIRONMENT_KEYS = (
    "MEMORY_RETRIEVAL_MODE", "OLLAMA_EMBEDDING_MODEL",
    "MEMORY_EMBEDDING_TIMEOUT_SECONDS", "MEMORY_SEMANTIC_MIN_SIMILARITY",
)


@dataclass(frozen=True)
class MemorySettings:
    mode: str
    embedding_model: str
    timeout_seconds: float
    min_similarity: float


def get_memory_settings() -> MemorySettings:
    mode = os.getenv("MEMORY_RETRIEVAL_MODE", "keyword").strip().lower()
    if mode not in {"keyword", "semantic"}:
        raise ValueError("MEMORY_RETRIEVAL_MODE must be 'keyword' or 'semantic'.")
    model = os.getenv("OLLAMA_EMBEDDING_MODEL", "embeddinggemma").strip()
    if not model:
        raise ValueError("OLLAMA_EMBEDDING_MODEL must not be blank.")
    try:
        timeout = float(os.getenv("MEMORY_EMBEDDING_TIMEOUT_SECONDS", "60"))
    except ValueError as error:
        raise ValueError("MEMORY_EMBEDDING_TIMEOUT_SECONDS must be a positive finite number.") from error
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("MEMORY_EMBEDDING_TIMEOUT_SECONDS must be a positive finite number.")
    try:
        minimum = float(os.getenv("MEMORY_SEMANTIC_MIN_SIMILARITY", "0.35"))
    except ValueError as error:
        raise ValueError("MEMORY_SEMANTIC_MIN_SIMILARITY must be between 0 and 1.") from error
    if not math.isfinite(minimum) or not 0 <= minimum <= 1:
        raise ValueError("MEMORY_SEMANTIC_MIN_SIMILARITY must be between 0 and 1.")
    return MemorySettings(mode, model, timeout, minimum)
