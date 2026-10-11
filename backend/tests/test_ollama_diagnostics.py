"""Exercise model metadata, timeout and isolation semantics without inference."""

import json

import pytest
import requests
from sqlalchemy import event

from app.models.agent import Agent
from app.services import ollama_diagnostics as service
from test_conversation_pagination import database_rows
from test_mcp_runtime_api import demo_api  # noqa: F401


def response(body=None, *, status=200, raw=None):
    value = requests.Response()
    value.status_code = status
    value._content = json.dumps(body if body is not None else {"models": [
        {"name": "qwen2.5:7b", "model": "qwen2.5:7b"}, {"name": "embeddinggemma:latest"}]}).encode() if raw is None else raw
    value._content_consumed = True
    return value


@pytest.fixture
def inventory(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    state = {"response": response(), "error": None, "calls": []}
    class Client:
        trust_env = True
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url, **kwargs):
            state["calls"].append((url, kwargs, self.trust_env))
            if state["error"] is not None: raise state["error"]
            return state["response"]
    monkeypatch.setattr(service.requests, "Session", Client)
    return state


def read(client, agent_id=None):
    result = client.get("/runtime/ollama", params={} if agent_id is None else {"agent_id": agent_id})
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "no-store" and result.headers["x-content-type-options"] == "nosniff"
    return result.json()


def test_explicit_read_uses_one_metadata_get_and_preserves_all_records(demo_api, inventory, monkeypatch):
    client, ids, sessions = demo_api
    monkeypatch.setenv("MEMORY_RETRIEVAL_MODE", "semantic")
    before = database_rows(sessions)
    value = read(client, ids["agent_id"])
    assert value["read_only"] is True and value["inference_performed"] is False and value["model_probe_performed"] is True
    assert value["connection_status"] == "available" and value["model_count"] == 2
    assert all(item["status"] == "installed" for item in value["models"].values())
    assert value["models"]["embedding"]["installed_name"] == "embeddinggemma:latest"
    assert inventory["calls"] == [("http://localhost:11434/api/tags", {"timeout": 5.0, "allow_redirects": False, "stream": True}, False)]
    assert database_rows(sessions) == before


def test_keyword_mode_does_not_require_an_embedding_model(demo_api, inventory):
    client, ids, _ = demo_api
    value = read(client, ids["agent_id"])
    assert value["models"]["embedding"]["status"] == "not_required"
    assert value["models"]["embedding"]["installed_name"] is None


@pytest.mark.parametrize("mode", ["keyword", "semantic"])
def test_mock_provider_never_contacts_ollama(demo_api, monkeypatch, mode):
    client, ids, sessions = demo_api
    monkeypatch.setenv("MEMORY_RETRIEVAL_MODE", mode)
    before = database_rows(sessions)
    value = read(client, ids["agent_id"])
    assert value["connection_status"] == "not_required" and value["model_probe_performed"] is False
    assert all(item["status"] == "not_required" for item in value["models"].values())
    assert read(client)["models"]["chat"] == {"configured_model": None, "status": "not_selected", "installed_name": None}
    assert database_rows(sessions) == before


def test_global_and_selected_agent_use_their_own_saved_model(demo_api, inventory):
    client, ids, sessions = demo_api
    with sessions() as db:
        db.get(Agent, ids["agent_id"]).model = "another-chat:7b"
        db.commit()
    before = database_rows(sessions)
    assert read(client)["models"]["chat"]["status"] == "not_selected"
    own = read(client, ids["agent_id"])
    other = read(client, ids["mcp_agent_id"])
    assert own["models"]["chat"] == {"configured_model": "another-chat:7b", "status": "missing", "installed_name": None}
    assert other["models"]["chat"]["status"] == "installed"
    assert database_rows(sessions) == before


def test_explicit_tags_do_not_match_other_tags_or_double_latest_suffix(demo_api, inventory):
    client, ids, _ = demo_api
    inventory["response"] = response({"models": [{"name": "qwen2.5:14b"}, {"name": "qwen2.5:7b:latest"}]})
    value = read(client, ids["agent_id"])
    assert value["models"]["chat"]["status"] == value["models"]["planner"]["status"] == "missing"


def test_empty_inventory_means_missing_and_refresh_does_not_cache_it(demo_api, inventory):
    client, ids, _ = demo_api
    inventory["response"] = response({"models": []})
    assert read(client, ids["agent_id"])["models"]["chat"]["status"] == "missing"
    inventory["response"] = response()
    assert read(client, ids["agent_id"])["models"]["chat"]["status"] == "installed"
    assert len(inventory["calls"]) == 2


@pytest.mark.parametrize("error,status", [(requests.Timeout("private-url-token"), "timeout"),
                                         (requests.ConnectionError("private-url-token"), "unreachable")])
def test_transport_failure_is_unknown_and_redacted(demo_api, inventory, monkeypatch, error, status):
    client, ids, sessions = demo_api
    monkeypatch.setenv("MEMORY_RETRIEVAL_MODE", "semantic")
    before = database_rows(sessions)
    inventory["error"] = error
    value = read(client, ids["agent_id"])
    assert value["connection_status"] == status and value["model_count"] is None
    assert all(item["status"] == "unknown" for item in value["models"].values())
    assert "private-url-token" not in json.dumps(value) and database_rows(sessions) == before


@pytest.mark.parametrize("status", [301, 302, 307, 401, 404, 500])
def test_non_success_or_redirect_is_not_followed_and_never_exposes_its_body(demo_api, inventory, status):
    client, ids, _ = demo_api
    inventory["response"] = response(status=status, raw=b'private-password-upstream-body')
    value = read(client, ids["agent_id"])
    assert value["connection_status"] == "http_error" and value["models"]["chat"]["status"] == "unknown"
    assert "private-password" not in json.dumps(value) and len(inventory["calls"]) == 1


@pytest.mark.parametrize("body", [[], {"models": None}, {"models": [None]}, {"models": [{}]},
                                 {"models": [{"name": 1}]}, {"models": [{"name": " "}]},
                                 {"models": [{"name": "qwen2.5:7b", "model": "another:7b"}]},
                                 {"models": [{"name": "x"}] * 1001}])
def test_malformed_or_oversized_inventory_is_not_reported_as_missing(demo_api, inventory, body):
    client, ids, _ = demo_api
    inventory["response"] = response(body)
    value = read(client, ids["agent_id"])
    assert value["connection_status"] == "invalid_response" and value["models"]["chat"]["status"] == "unknown"


@pytest.mark.parametrize("raw", [b'not-json-private-secret', b' ' * (1024 * 1024 + 1)])
def test_invalid_json_and_large_response_are_bounded_and_redacted(demo_api, inventory, raw):
    client, ids, _ = demo_api
    inventory["response"] = response(raw=raw)
    assert read(client, ids["agent_id"])["connection_status"] == "invalid_response"


@pytest.mark.parametrize("agent,status", [(0, 422), (-1, 422), ("bad", 422), ("1.5", 422),
                                         (9223372036854775808, 422), (9223372036854775807, 404)])
def test_invalid_agent_stops_before_any_metadata_request(demo_api, inventory, agent, status):
    client, _, sessions = demo_api
    before = database_rows(sessions)
    assert client.get("/runtime/ollama", params={"agent_id": agent}).status_code == status
    assert inventory["calls"] == [] and database_rows(sessions) == before


@pytest.mark.parametrize("key,value", [("LLM_PROVIDER", "private-provider"), ("OLLAMA_BASE_URL", "bad"),
                                       ("OLLAMA_TIMEOUT_SECONDS", "nan"), ("MEMORY_RETRIEVAL_MODE", "bad")])
def test_invalid_configuration_is_redacted_without_a_probe(demo_api, inventory, monkeypatch, key, value):
    client, _, _ = demo_api
    monkeypatch.setenv(key, value)
    result = client.get("/runtime/ollama")
    assert result.status_code == 503 and "private-provider" not in result.text
    assert result.headers["cache-control"] == "no-store" and inventory["calls"] == []


def test_existing_settings_and_health_still_do_not_probe(demo_api, inventory):
    client, _, _ = demo_api
    assert client.get("/runtime/config").json()["model_probe_performed"] is False
    assert client.get("/health").json() == {"status": "ok"}
    assert inventory["calls"] == []


def test_only_scoped_agent_select_is_used_and_short_configured_timeout_is_respected(demo_api, inventory, monkeypatch):
    client, ids, sessions = demo_api
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "0.25")
    with sessions() as db: engine = db.get_bind()
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
    assert inventory["calls"][-1][1]["timeout"] == 0.25
