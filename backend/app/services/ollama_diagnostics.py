"""One explicit, bounded GET of the configured Ollama model inventory."""

import json
import time

import requests

from app.config import get_llm_settings
from app.memory_config import get_memory_settings
from app.models.agent import Agent
from app.schemas.ollama_diagnostics import (
    OllamaDiagnosticsResponse, OllamaModelChecks, OllamaModelObservation, canonical_model_name,
)


MAX_INVENTORY_BYTES = 1024 * 1024
MAX_MODELS = 1000


def read_inventory(base_url: str, timeout: float) -> tuple[str, dict[str, str] | None]:
    """Do not follow redirects, use shell proxies or return upstream error text."""
    timeout = min(5.0, timeout)
    deadline = time.monotonic() + timeout
    try:
        with requests.Session() as client:
            client.trust_env = False
            with client.get(base_url + "/api/tags", timeout=timeout, allow_redirects=False, stream=True) as response:
                if response.status_code != 200:
                    return "http_error", None
                chunks, size = [], 0
                for chunk in response.iter_content(chunk_size=8192):
                    if time.monotonic() > deadline:
                        return "timeout", None
                    size += len(chunk)
                    if size > MAX_INVENTORY_BYTES:
                        return "invalid_response", None
                    chunks.append(chunk)
                value = json.loads(b"".join(chunks))
        rows = value.get("models") if isinstance(value, dict) else None
        if not isinstance(rows, list) or len(rows) > MAX_MODELS:
            return "invalid_response", None
        inventory = {}
        for row in rows:
            if not isinstance(row, dict):
                return "invalid_response", None
            names = [row[key] for key in ("name", "model") if key in row]
            if not names or any(not isinstance(name, str) or not name.strip() for name in names):
                return "invalid_response", None
            if len({canonical_model_name(name) for name in names}) != 1:
                return "invalid_response", None
            inventory.setdefault(canonical_model_name(names[0]), names[0])
        return "available", inventory
    except requests.Timeout:
        return "timeout", None
    except requests.RequestException:
        return "unreachable", None
    except (ValueError, UnicodeError):
        return "invalid_response", None


def ollama_diagnostics(agent: Agent | None = None) -> OllamaDiagnosticsResponse:
    llm, memory = get_llm_settings(), get_memory_settings()
    mock = llm.provider == "mock"
    connection, inventory = ("not_required", None) if mock else read_inventory(llm.ollama_base_url, llm.timeout_seconds)

    def observe(model, *, selected=True, required=True):
        if not selected:
            return OllamaModelObservation(configured_model=None, status="not_selected")
        if mock or not required:
            status, installed = "not_required", None
        elif not model or not model.strip():
            status, installed = "not_configured", None
        elif inventory is None:
            status, installed = "unknown", None
        else:
            installed = inventory.get(canonical_model_name(model))
            status = "installed" if installed is not None else "missing"
        return OllamaModelObservation(configured_model=model, status=status, installed_name=installed)

    return OllamaDiagnosticsResponse(
        llm_provider=llm.provider,
        model_probe_performed=not mock,
        selected_agent_id=None if agent is None else agent.id,
        memory_retrieval_mode=memory.mode,
        connection_status=connection,
        model_count=None if inventory is None else len(inventory),
        models=OllamaModelChecks(
            chat=observe(None if agent is None else agent.model, selected=agent is not None),
            planner=observe(llm.planner_model),
            embedding=observe(memory.embedding_model, required=memory.mode == "semantic"),
        ),
    )
