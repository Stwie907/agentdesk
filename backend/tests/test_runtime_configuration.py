"""Settings reads preserve all data and never contact a model provider."""

import pytest
from sqlalchemy import event

from app.models.agent import Agent
from test_conversation_pagination import database_rows
from test_mcp_runtime_api import demo_api  # noqa: F401


def read(client, agent_id=None):
    response = client.get("/runtime/config", params={} if agent_id is None else {"agent_id": agent_id})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    return response.json()


def test_default_ollama_configuration_is_global_and_read_only(demo_api, monkeypatch):
    client, _, sessions = demo_api
    monkeypatch.delenv("LLM_PROVIDER")
    before = database_rows(sessions)
    value = read(client)
    assert value == {
        "schema_version": 1, "read_only": True, "model_probe_performed": False,
        "llm_provider": "ollama", "configured_planner_model": "qwen2.5:7b", "selected_agent": None,
        "memory": {"retrieval_mode": "keyword", "configured_embedding_model": "embeddinggemma",
                   "active_embedding_model": None, "min_similarity": 0.35,
                   "vector_cache_enabled": True, "vector_cache_active": False},
        "database_backend": "sqlite",
    }
    assert database_rows(sessions) == before
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("provider", ["ollama", "mock"])
@pytest.mark.parametrize("mode", ["keyword", "semantic"])
@pytest.mark.parametrize("cache", [True, False])
def test_reports_effective_embedding_and_cache_activity_without_model_probes(demo_api, monkeypatch, provider, mode, cache):
    client, ids, sessions = demo_api
    monkeypatch.setenv("LLM_PROVIDER", " " + provider.upper() + " ")
    monkeypatch.setenv("MEMORY_RETRIEVAL_MODE", mode)
    monkeypatch.setenv("MEMORY_VECTOR_CACHE_ENABLED", str(cache).lower())
    monkeypatch.setenv("OLLAMA_EMBEDDING_MODEL", "local-embedding-model")
    monkeypatch.setenv("MEMORY_SEMANTIC_MIN_SIMILARITY", "0.75")
    before = database_rows(sessions)
    value = read(client, ids["agent_id"])
    assert value["llm_provider"] == provider
    assert value["selected_agent"] == {"id": ids["agent_id"], "chat_model": "qwen2.5:7b"}
    memory = value["memory"]
    assert memory["configured_embedding_model"] == "local-embedding-model" and memory["min_similarity"] == 0.75
    assert memory["active_embedding_model"] == (None if mode == "keyword" else "mock-fixtures-v1" if provider == "mock" else "local-embedding-model")
    assert memory["vector_cache_enabled"] is cache
    assert memory["vector_cache_active"] is (mode == "semantic" and cache)
    assert value["model_probe_performed"] is False and database_rows(sessions) == before


def test_chat_model_is_the_selected_agents_saved_model_and_settings_refresh(demo_api, monkeypatch):
    client, ids, sessions = demo_api
    with sessions() as db:
        db.get(Agent, ids["agent_id"]).model = "another-local-chat-model"
        db.commit()
    monkeypatch.setenv("OLLAMA_PLANNER_MODEL", "local-planning-model")
    before = database_rows(sessions)
    own = read(client, ids["agent_id"])
    other = read(client, ids["mcp_agent_id"])
    assert own["selected_agent"]["chat_model"] == "another-local-chat-model"
    assert own["configured_planner_model"] == "local-planning-model"
    assert other["selected_agent"]["id"] == ids["mcp_agent_id"]
    assert other["selected_agent"]["chat_model"] == "qwen2.5:7b"
    monkeypatch.setenv("MEMORY_RETRIEVAL_MODE", "semantic")
    assert read(client)["memory"]["active_embedding_model"] == "mock-fixtures-v1"
    assert database_rows(sessions) == before


def test_no_endpoints_credentials_paths_or_unrelated_environment_are_exposed(demo_api, monkeypatch):
    client, ids, sessions = demo_api
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://private-user:private-password@localhost:11434")
    monkeypatch.setenv("OPENAI_API_KEY", "private-paid-api-key")
    before = database_rows(sessions)
    response = client.get("/runtime/config", params={"agent_id": ids["agent_id"]})
    assert response.status_code == 200
    for secret in ("private-user", "private-password", "private-paid-api-key", "localhost", "11434", "sqlite://", "database_url", "ollama_base_url"):
        assert secret not in response.text.lower()
    assert database_rows(sessions) == before


@pytest.mark.parametrize("key,value", [
    ("LLM_PROVIDER", "paid-provider-secret"), ("OLLAMA_BASE_URL", "private-invalid-url"),
    ("OLLAMA_PLANNER_MODEL", " "), ("OLLAMA_TIMEOUT_SECONDS", "nan"),
    ("MEMORY_RETRIEVAL_MODE", "hybrid"), ("OLLAMA_EMBEDDING_MODEL", " "),
    ("MEMORY_EMBEDDING_TIMEOUT_SECONDS", "0"), ("MEMORY_SEMANTIC_MIN_SIMILARITY", "nan"),
    ("MEMORY_VECTOR_CACHE_ENABLED", "1"),
])
def test_invalid_settings_have_a_redacted_503_and_do_not_affect_liveness_or_data(demo_api, monkeypatch, key, value):
    client, _, sessions = demo_api
    monkeypatch.setenv(key, value)
    before = database_rows(sessions)
    response = client.get("/runtime/config")
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"detail": "Runtime configuration is invalid. Check LLM and memory environment settings."}
    assert "private" not in response.text and "paid-provider-secret" not in response.text
    assert client.get("/health").json() == {"status": "ok"}
    assert database_rows(sessions) == before


@pytest.mark.parametrize("agent,status", [(0, 422), (-1, 422), ("invalid", 422), ("1.5", 422),
                                         (9223372036854775808, 422), (9223372036854775807, 404)])
def test_invalid_or_deleted_agent_is_explicit_and_never_selects_another_agent(demo_api, agent, status):
    client, _, sessions = demo_api
    before = database_rows(sessions)
    response = client.get("/runtime/config", params={"agent_id": agent})
    assert response.status_code == status
    assert database_rows(sessions) == before


def test_global_view_uses_no_sql_and_agent_view_uses_only_one_select(demo_api):
    client, ids, sessions = demo_api
    with sessions() as db:
        engine = db.get_bind()
    statements = []
    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.lstrip().upper())
    event.listen(engine, "before_cursor_execute", capture)
    try:
        read(client)
        assert statements == []
        read(client, ids["agent_id"])
        assert len(statements) == 1 and statements[0].startswith("SELECT")
    finally:
        event.remove(engine, "before_cursor_execute", capture)


def test_malformed_then_repaired_environment_can_be_read_without_a_cached_failure(demo_api, monkeypatch):
    client, _, _ = demo_api
    monkeypatch.setenv("LLM_PROVIDER", "invalid")
    assert client.get("/runtime/config").status_code == 503
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    assert read(client)["llm_provider"] == "mock"
