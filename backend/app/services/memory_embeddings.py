"""Local Ollama /api/embed client with explicitly limited offline Mock fixtures."""

from dataclasses import dataclass
import math

import requests

from app.config import get_llm_settings
from app.memory_config import MemorySettings, get_memory_settings


class SemanticMemoryUnavailable(RuntimeError):
    pass


# These vectors exercise the pipeline; they are not a learned embedding model.
MOCK_VECTORS = {
    "I prefer concise answers.": (1, 0, 0, 0),
    "我喜欢简洁的回答。": (1, 0, 0, 0),
    "Keep it brief.": (0.96, 0.28, 0, 0),
    "请用简短的方式解释。": (0.96, 0.28, 0, 0),
    "SQLite records survive restarts.": (0, 1, 0, 0),
    "Can saved information stay after reboot?": (0.1, 0.99, 0, 0),
    "Unrelated semantic fixture.": (0, 0, 1, 0),
}
MOCK_QUERIES = {"Keep it brief.", "请用简短的方式解释。",
                "Can saved information stay after reboot?", "Unrelated semantic fixture."}


def mock_vector(text: str):
    prefix, separator, fixture = text.partition(" | ")
    token = prefix.removeprefix("AgentDeskSemanticTemporary ")
    if separator and prefix.startswith("AgentDeskSemanticTemporary ") and len(token) == 32 and all(char in "0123456789abcdef" for char in token):
        text = fixture
    return MOCK_VECTORS.get(text, (0, 0, 0, 1))


@dataclass(frozen=True)
class EmbeddingSettings:
    provider: str
    model: str
    base_url: str
    memory: MemorySettings


def get_embedding_settings() -> EmbeddingSettings:
    try:
        llm, memory = get_llm_settings(), get_memory_settings()
    except ValueError as error:
        raise SemanticMemoryUnavailable(str(error)) from error
    return EmbeddingSettings(llm.provider, "mock-fixtures-v1" if llm.provider == "mock" else memory.embedding_model,
                             llm.ollama_base_url, memory)


def normalize_vector(value) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)) or not value or len(value) > 16384:
        raise SemanticMemoryUnavailable("Embedding vectors must be non-empty numeric arrays.")
    if any(type(number) not in (int, float) for number in value):
        raise SemanticMemoryUnavailable("Embedding vectors must contain finite numbers.")
    try:
        value = tuple(float(number) for number in value)
        if not all(math.isfinite(number) for number in value):
            raise SemanticMemoryUnavailable("Embedding vectors must contain finite numbers.")
        norm = math.hypot(*value)
    except (OverflowError, TypeError) as error:
        raise SemanticMemoryUnavailable("Embedding vector magnitude is invalid.") from error
    if not math.isfinite(norm) or norm == 0:
        raise SemanticMemoryUnavailable("Embedding vectors must have a finite non-zero magnitude.")
    return tuple(number / norm for number in value)


def embed_texts(texts: list[str], settings: EmbeddingSettings) -> list[tuple[float, ...]]:
    if not texts:
        return []
    if settings.provider == "mock":
        return [normalize_vector(mock_vector(text)) for text in texts]
    vectors = []
    # Bound individual HTTP payloads without dropping owner-scoped records.
    with requests.Session() as client:
        client.trust_env = False
        for offset in range(0, len(texts), 32):
            batch = texts[offset:offset + 32]
            try:
                response = client.post(settings.base_url + "/api/embed",
                    json={"model": settings.model, "input": batch, "truncate": False},
                    timeout=settings.memory.timeout_seconds, allow_redirects=False)
                if response.status_code == 404:
                    raise SemanticMemoryUnavailable("Embedding model or /api/embed is unavailable. Install the configured local model and check Ollama.")
                if not 200 <= response.status_code < 300:
                    raise SemanticMemoryUnavailable("Ollama rejected the embedding request. Check model support and input length.")
                body = response.json()
            except requests.Timeout as error:
                raise SemanticMemoryUnavailable("Local embedding request timed out. Check Ollama or increase the embedding timeout.") from error
            except requests.RequestException as error:
                raise SemanticMemoryUnavailable("Unable to connect to local Ollama embeddings.") from error
            except ValueError as error:
                raise SemanticMemoryUnavailable("Ollama embeddings returned invalid JSON.") from error
            values = body.get("embeddings") if isinstance(body, dict) else None
            if not isinstance(values, list) or len(values) != len(batch):
                raise SemanticMemoryUnavailable("Ollama returned the wrong number of embedding vectors.")
            if not isinstance(body.get("model"), str) or body["model"] not in {settings.model, settings.model + ":latest"}:
                raise SemanticMemoryUnavailable("Ollama returned a different embedding model.")
            vectors.extend(normalize_vector(value) for value in values)
    if len({len(vector) for vector in vectors}) != 1:
        raise SemanticMemoryUnavailable("Ollama embedding dimensions changed within the request.")
    return vectors
