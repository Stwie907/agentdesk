import os
import math
from dataclasses import dataclass
from urllib.parse import urlsplit


APP_NAME = "AgentDesk Backend"

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./agentdesk.db",
)


LLM_ENVIRONMENT_KEYS = (
    "LLM_PROVIDER",
    "OLLAMA_BASE_URL",
    "OLLAMA_PLANNER_MODEL",
    "OLLAMA_TIMEOUT_SECONDS",
)


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    ollama_base_url: str
    planner_model: str
    timeout_seconds: float

    @property
    def generate_url(self) -> str:
        return f"{self.ollama_base_url}/api/generate"


def get_llm_settings() -> LLMSettings:
    """Read process environment settings without caching provider selection."""
    provider = os.getenv("LLM_PROVIDER", "ollama").strip().lower()

    if provider not in {"ollama", "mock"}:
        raise ValueError("LLM_PROVIDER must be 'ollama' or 'mock'.")

    base_url = os.getenv(
        "OLLAMA_BASE_URL", "http://localhost:11434",
    ).strip().rstrip("/")
    parsed_url = urlsplit(base_url)

    if (
        parsed_url.scheme not in {"http", "https"}
        or not parsed_url.hostname
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise ValueError("OLLAMA_BASE_URL must be an HTTP(S) base URL.")

    planner_model = os.getenv("OLLAMA_PLANNER_MODEL", "qwen2.5:7b").strip()

    if not planner_model:
        raise ValueError("OLLAMA_PLANNER_MODEL must not be blank.")

    try:
        timeout_seconds = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))
    except ValueError as error:
        raise ValueError("OLLAMA_TIMEOUT_SECONDS must be a positive finite number.") from error

    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("OLLAMA_TIMEOUT_SECONDS must be a positive finite number.")

    return LLMSettings(
        provider=provider,
        ollama_base_url=base_url,
        planner_model=planner_model,
        timeout_seconds=timeout_seconds,
    )
