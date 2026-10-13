"""Vector protocol, read-only scope, Runtime integration, and explicit fallback."""

import math
from types import SimpleNamespace

import pytest
import requests

from app.memory_config import get_memory_settings
from app.models.execution_log import ExecutionLog
from app.services import memory_embeddings, semantic_memory
from app.services.memory_embeddings import SemanticMemoryUnavailable, embed_texts, get_embedding_settings, normalize_vector
from app.services.memory_service import build_memory_context
from app.workers import execution_worker
from test_mcp_runtime_api import demo_api  # noqa: F401
from test_user_memory import add_agent


def save(client, agent_id, content):
    response = client.post("/memories", json={"agent_id": agent_id, "content": content})
    assert response.status_code == 200
    return response.json()


def shared(client, agent_id, owner_id, content):
    response = client.post(f"/user-memories/for-agent/{agent_id}", json={"user_id": owner_id, "content": content})
    assert response.status_code == 200
    return response.json()


def search(client, agent_id, query="Keep it brief.", user=False, **params):
    prefix = f"/user-memories/for-agent/{agent_id}" if user else f"/memories/{agent_id}"
    return client.get(prefix + "/semantic-search", params={"query": query, **params})


def test_defaults_preserve_keyword_mode_and_qwen_chat_model():
    settings = get_memory_settings()
    assert (settings.mode, settings.embedding_model, settings.timeout_seconds, settings.min_similarity) == ("keyword", "embeddinggemma", 60, 0.35)
    from app.config import get_llm_settings
    assert get_llm_settings().planner_model == "qwen2.5:7b"


@pytest.mark.parametrize("key,value", [
    ("MEMORY_RETRIEVAL_MODE", "unknown"), ("OLLAMA_EMBEDDING_MODEL", " "),
    ("MEMORY_EMBEDDING_TIMEOUT_SECONDS", "0"), ("MEMORY_EMBEDDING_TIMEOUT_SECONDS", "nan"),
    ("MEMORY_EMBEDDING_TIMEOUT_SECONDS", "inf"), ("MEMORY_EMBEDDING_TIMEOUT_SECONDS", "bad"),
    ("MEMORY_SEMANTIC_MIN_SIMILARITY", "-0.1"), ("MEMORY_SEMANTIC_MIN_SIMILARITY", "1.1"),
    ("MEMORY_SEMANTIC_MIN_SIMILARITY", "nan"), ("MEMORY_SEMANTIC_MIN_SIMILARITY", "bad"),
])
def test_invalid_configuration_is_rejected(monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError, match=key): get_memory_settings()


@pytest.mark.parametrize("vector", [[], [0, 0], [True, 1], ["1", 0], [None], [math.nan], [math.inf], [10 ** 400], {}, [1] * 16385])
def test_invalid_vectors_are_rejected_without_nan_scores(vector):
    with pytest.raises(SemanticMemoryUnavailable): normalize_vector(vector)


def test_normalization_handles_large_and_small_finite_values():
    assert normalize_vector([3, 4]) == (0.6, 0.8)
    assert normalize_vector([1e308, 0]) == (1.0, 0.0)
    assert normalize_vector([5e-324, 0]) == (1.0, 0.0)


def test_ollama_batches_are_bounded_and_bypass_proxy_environment(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.setenv("MEMORY_EMBEDDING_TIMEOUT_SECONDS", "2.5")
    captured = []
    def post(client, url, **kwargs):
        captured.append((client.trust_env, url, kwargs))
        return SimpleNamespace(status_code=200, json=lambda: {"model": "embeddinggemma:latest",
            "embeddings": [[3, 4] for _ in kwargs["json"]["input"]]})
    monkeypatch.setattr(requests.Session, "post", post)
    vectors = embed_texts(["text " + str(index) for index in range(65)], get_embedding_settings())
    assert vectors == [(0.6, 0.8)] * 65
    assert [len(call[2]["json"]["input"]) for call in captured] == [32, 32, 1]
    assert all(call[0] is False and call[1].endswith("/api/embed") and call[2]["json"]["truncate"] is False
               and call[2]["timeout"] == 2.5 and call[2]["allow_redirects"] is False for call in captured)


@pytest.mark.parametrize("failure", ["timeout", "connection", "status", "redirect", "missing_model", "json", "count", "dimensions", "wrong_model", "invalid_model"])
def test_ollama_failures_are_explicit_and_never_select_mock(monkeypatch, failure):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    def post(*args, **kwargs):
        if failure == "timeout": raise requests.Timeout("slow")
        if failure == "connection": raise requests.ConnectionError("offline")
        status = {"status": 500, "redirect": 302, "missing_model": 404}.get(failure, 200)
        def body():
            if failure == "json": raise ValueError("invalid JSON")
            if failure == "count": return {"model": "embeddinggemma", "embeddings": [[1, 0]]}
            if failure == "dimensions": return {"model": "embeddinggemma", "embeddings": [[1, 0], [1, 0, 0]]}
            model = [] if failure == "invalid_model" else "wrong" if failure == "wrong_model" else "embeddinggemma"
            return {"model": model, "embeddings": [[1, 0], [1, 0]]}
        return SimpleNamespace(status_code=status, json=body)
    monkeypatch.setattr(requests.Session, "post", post)
    with pytest.raises(SemanticMemoryUnavailable): embed_texts(["query", "memory"], get_embedding_settings())


def test_fixture_search_finds_synonyms_and_chinese_without_keyword_overlap(demo_api):
    client, ids, _ = demo_api
    english = save(client, ids["agent_id"], "I prefer concise answers.")
    chinese = save(client, ids["agent_id"], "我喜欢简洁的回答。")
    keyword = client.get(f'/memories/{ids["agent_id"]}/search', params={"query": "Keep it brief."}).json()
    assert keyword["results"] == []
    result = search(client, ids["agent_id"], "  Keep it brief.  ").json()
    assert result["mode"] == "semantic" and result["provider"] == "mock" and result["model"] == "mock-fixtures-v1"
    assert result["runtime_mode"] == "keyword" and result["query"] == "Keep it brief."
    assert result["results"] == [{"memory": chinese, "similarity": 0.96}, {"memory": english, "similarity": 0.96}]
    assert search(client, ids["agent_id"], "请用简短的方式解释。", limit=1).json()["results"] == result["results"][:1]
    assert search(client, ids["agent_id"], min_similarity=0.97).json()["results"] == []
    assert search(client, ids["agent_id"], "Unrelated semantic fixture.").json()["results"] == []
    assert search(client, ids["agent_id"], "Unsupported Mock query").status_code == 503


def test_scope_is_filtered_before_any_embedding_request(demo_api, monkeypatch):
    client, ids, sessions = demo_api
    own = save(client, ids["agent_id"], "Own private text")
    save(client, ids["mcp_agent_id"], "Another Agent private secret")
    outsider, foreign_owner = add_agent(sessions)
    shared(client, outsider, foreign_owner, "Other user's private secret")
    same = shared(client, ids["agent_id"], ids["user_id"], "Own shared text")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    inputs = []
    def post(client, url, **kwargs):
        inputs.append(kwargs["json"]["input"])
        return SimpleNamespace(status_code=200, json=lambda: {"model": "embeddinggemma", "embeddings": [[1, 0] for _ in inputs[-1]]})
    monkeypatch.setattr(requests.Session, "post", post)
    assert search(client, ids["agent_id"]).json()["results"][0]["memory"] == own
    assert search(client, ids["mcp_agent_id"], user=True).json()["results"][0]["memory"] == same
    assert inputs == [["Keep it brief.", own["content"]], ["Keep it brief.", same["content"]]]
    assert search(client, 999999).status_code == 404
    assert len(inputs) == 2


def test_shared_preview_shares_owner_records_and_preserves_all_inspection_data(demo_api):
    client, ids, sessions = demo_api
    outsider, _ = add_agent(sessions)
    memory = shared(client, ids["agent_id"], ids["user_id"], "I prefer concise answers.")
    conversation = client.post("/conversations", json={"agent_id": ids["agent_id"], "title": "Preserve"}).json()
    chat = client.post(f'/conversations/{conversation["id"]}/chat', json={"message": "Hello"}).json()
    paths = [f'/conversations/{conversation["id"]}/messages', f'/memories/{ids["agent_id"]}',
             f'/user-memories/for-agent/{ids["agent_id"]}', f'/executions?agent_id={ids["agent_id"]}',
             *(f'/executions/{chat["execution_id"]}' + suffix for suffix in ("", "/trace", "/snapshot"))]
    before = {path: client.get(path).json() for path in paths}
    assert search(client, ids["mcp_agent_id"], user=True).json()["results"][0]["memory"] == memory
    assert search(client, outsider, user=True).json()["results"] == []
    assert {path: client.get(path).json() for path in paths} == before


@pytest.mark.parametrize("params", [{"query": " "}, {"query": "x" * 501}, {"query": "Keep it brief.", "limit": 0},
    {"query": "Keep it brief.", "limit": 21}, {"query": "Keep it brief.", "min_similarity": -0.1},
    {"query": "Keep it brief.", "min_similarity": 1.1}, {"query": "Keep it brief.", "min_similarity": "nan"}])
def test_api_validation_is_read_only(demo_api, params):
    client, ids, _ = demo_api
    for prefix in (f'/memories/{ids["agent_id"]}', f'/user-memories/for-agent/{ids["agent_id"]}'):
        assert client.get(prefix + "/semantic-search", params=params).status_code == 422


def test_edit_and_delete_have_no_stale_vectors(demo_api):
    client, ids, _ = demo_api
    memory = save(client, ids["agent_id"], "I prefer concise answers.")
    assert search(client, ids["agent_id"]).json()["results"]
    changed = client.patch(f'/memories/item/{memory["id"]}?agent_id={ids["agent_id"]}',
        json={"content": "SQLite records survive restarts.", "expected_content": memory["content"]}).json()
    assert changed == {**memory, "content": "SQLite records survive restarts."}
    assert search(client, ids["agent_id"], min_similarity=0.35).json()["results"] == []
    assert search(client, ids["agent_id"], "Can saved information stay after reboot?").json()["results"][0]["memory"] == changed
    assert client.delete(f'/memories/item/{memory["id"]}?agent_id={ids["agent_id"]}').status_code == 200
    assert search(client, ids["agent_id"], "Can saved information stay after reboot?").json()["results"] == []


def test_semantic_runtime_receives_both_sources_and_ignores_other_owners(demo_api, monkeypatch):
    client, ids, sessions = demo_api
    outsider, foreign_owner = add_agent(sessions)
    private = save(client, ids["agent_id"], "I prefer concise answers.")
    same = shared(client, ids["agent_id"], ids["user_id"], "我喜欢简洁的回答。")
    shared(client, outsider, foreign_owner, "I prefer concise answers.")
    monkeypatch.setenv("MEMORY_RETRIEVAL_MODE", "semantic")
    captured = []
    original = execution_worker.run_agent
    def run(*args, **kwargs):
        captured.append(args[2]); return original(*args, **kwargs)
    monkeypatch.setattr(execution_worker, "run_agent", run)
    for agent in (ids["agent_id"], ids["mcp_agent_id"]):
        result = client.post(f"/agents/{agent}/chat", json={"message": "Keep it brief."}).json()
        assert result["status"] == "completed" and result["response"].startswith("[MOCK]")
        logs = client.get(f'/execution-logs/{result["execution_id"]}').json()
        assert not any(row["message"].startswith("memory_retrieval_fallback:") for row in logs)
    assert captured == [f'Shared user memory:\n{same["content"]}\nAgent memory:\n{private["content"]}',
                        f'Shared user memory:\n{same["content"]}']


@pytest.mark.parametrize("configuration", ["service", "configuration"])
def test_runtime_falls_back_and_logs_without_leaving_execution_running(demo_api, monkeypatch, configuration):
    client, ids, sessions = demo_api
    private = save(client, ids["agent_id"], "Python keyword fallback")
    monkeypatch.setenv("MEMORY_RETRIEVAL_MODE", "semantic" if configuration == "service" else "invalid")
    if configuration == "service":
        monkeypatch.setattr(semantic_memory, "embed_texts", lambda *args: (_ for _ in ()).throw(SemanticMemoryUnavailable("Offline embedding service")))
        query = "Keep it brief."
    else:
        query = "Python"
    with sessions() as db:
        reasons = []
        text = build_memory_context(db, ids["agent_id"], query, on_fallback=reasons.append)
        assert reasons and text == ("" if configuration == "service" else private["content"])
    result = client.post(f'/agents/{ids["agent_id"]}/chat', json={"message": query}).json()
    assert result["status"] == "completed"
    logs = client.get(f'/execution-logs/{result["execution_id"]}').json()
    assert any(row["message"].startswith("memory_retrieval_fallback:") for row in logs)
    with sessions() as db:
        warning = db.query(ExecutionLog).filter(ExecutionLog.execution_id == result["execution_id"],
                                               ExecutionLog.message.like("memory_retrieval_fallback:%")).first()
        assert warning.level == "warning"


def test_explicit_semantic_preview_returns_503_and_never_keyword_results(demo_api, monkeypatch):
    client, ids, _ = demo_api
    save(client, ids["agent_id"], "I prefer concise answers.")
    monkeypatch.setattr(semantic_memory, "embed_texts", lambda *args: (_ for _ in ()).throw(SemanticMemoryUnavailable("Offline embedding service")))
    response = search(client, ids["agent_id"])
    assert response.status_code == 503 and response.json() == {"detail": "Offline embedding service"}


def test_semantic_runtime_has_separate_result_budgets_for_both_sources(demo_api, monkeypatch):
    client, ids, sessions = demo_api
    for index in range(7):
        save(client, ids["agent_id"], "Agent scoped " + str(index))
        shared(client, ids["agent_id"], ids["user_id"], "User scoped " + str(index))
    monkeypatch.setenv("MEMORY_RETRIEVAL_MODE", "semantic")
    monkeypatch.setattr(semantic_memory, "embed_texts", lambda texts, settings: [(1.0, 0.0)] * len(texts))
    with sessions() as db:
        text = build_memory_context(db, ids["agent_id"], "Keep it brief.")
    assert text.count("User scoped") == text.count("Agent scoped") == 5
    assert "User scoped 0" not in text and "Agent scoped 0" not in text


def test_ollama_endpoint_protocol_over_real_local_http(monkeypatch):
    import json
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            assert self.path == "/api/embed"
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert body == {"model": "embeddinggemma", "input": ["query", "record"], "truncate": False}
            payload = json.dumps({"model": "embeddinggemma", "embeddings": [[3, 4], [4, 3]]}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload)
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    try:
        assert embed_texts(["query", "record"], get_embedding_settings()) == [(0.6, 0.8), (0.8, 0.6)]
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def test_acceptance_initial_repeat_and_restart_reuse_fixtures_without_deleting_user_records(demo_api, tmp_path, monkeypatch):
    from app import check_demo, check_semantic_memory as acceptance, check_user_memory
    client, ids, _ = demo_api
    protected = [save(client, ids["agent_id"], text) for text in ("SQLite records survive restarts.", "Unrelated semantic fixture.", "Keep it brief.")]
    def read(base, path, payload=None):
        response = client.get(path) if payload is None else client.post(path, json=payload)
        assert response.status_code == 200, response.text
        return response.json()
    def request(base, path, payload=None, *, method=None, status=200):
        response = client.request(method or ("POST" if payload is not None else "GET"), path, json=payload)
        assert response.status_code == status, response.text
        return response.json()
    for module in (acceptance, check_demo, check_user_memory): monkeypatch.setattr(module, "request_json", read)
    monkeypatch.setattr(acceptance, "memory_request", request)
    path = tmp_path / "semantic-memory-acceptance.json"
    with pytest.raises(RuntimeError, match="MEMORY_RETRIEVAL_MODE"):
        acceptance.check_semantic_memory("http://demo", state_file=path)
    assert not path.exists()
    monkeypatch.setenv("MEMORY_RETRIEVAL_MODE", "semantic")
    first = acceptance.check_semantic_memory("http://demo", state_file=path)
    checkpoint = path.read_bytes()
    for persistence in (False, True):
        result = acceptance.check_semantic_memory("http://demo", persistence, path)
        assert result["checks_passed"] == 8 and result["memory_id"] == first["memory_id"]
        assert path.read_bytes() == checkpoint
    current = client.get(f'/memories/{ids["agent_id"]}').json()
    assert all(row in current for row in protected)


@pytest.mark.parametrize("loss", ["checkpoint", "invalid_checkpoint", "private", "shared", "isolated", "identity", "timestamp", "owner", "snapshot"])
def test_persistence_failures_are_read_only_before_replacement_writes(tmp_path, monkeypatch, loss):
    import json
    from urllib.error import HTTPError
    from app import check_semantic_memory as acceptance, check_user_memory
    private = {"id": 10, "agent_id": 1, "content": acceptance.PRIVATE, "created_at": "2026-10-09T08:00:00"}
    shared_memory = {"id": 20, "user_id": 1, "content": acceptance.SHARED, "created_at": private["created_at"]}
    isolated = {"id": 30, "user_id": 2, "content": acceptance.PRIVATE, "created_at": private["created_at"]}
    state = {"version": 1, "agent_id": 1, "peer_agent_id": 2, "user_id": 1, "isolation_agent_id": 3,
             "isolation_user_id": 2, "private": private, "shared": shared_memory, "isolated": isolated,
             "execution_id": 7, "inspection": {"": {"id": 7}, "/trace": [], "/snapshot": {"execution_id": 7}}}
    own = {"agent_id": 1, "user_id": 1, "memories": [dict(shared_memory)]}
    peer = {**own, "agent_id": 2}
    other = {"agent_id": 3, "user_id": 2, "memories": [dict(isolated)]}
    path = tmp_path / "semantic-memory-acceptance.json"
    if loss != "checkpoint": path.write_text(json.dumps({} if loss == "invalid_checkpoint" else state))
    current_private = [dict(private)]
    if loss == "private": current_private = []
    if loss == "shared": own["memories"] = []
    if loss == "isolated": other["memories"] = []
    if loss == "identity": current_private[0]["id"] += 1
    if loss == "timestamp": current_private[0]["created_at"] = "changed"
    if loss == "owner": other["user_id"] = 1
    responses = {"/agents": [{"id": 1, "name": "Demo Agent"}, {"id": 2, "name": "MCP Order Agent"}, {"id": 3, "name": "Other"}],
                 "/memories/1": current_private, "/user-memories/for-agent/1": own,
                 "/user-memories/for-agent/2": peer, "/user-memories/for-agent/3": other}
    for suffix, value in state["inspection"].items(): responses["/executions/7" + suffix] = value
    def read(base, requested, payload=None):
        assert payload is None, "Persistence validation attempted a new fixture write"
        if loss == "snapshot" and requested == "/executions/7/snapshot": raise HTTPError(requested, 404, "Not Found", {}, None)
        return responses[requested]
    for module in (acceptance, check_user_memory): monkeypatch.setattr(module, "request_json", read)
    monkeypatch.setattr(acceptance, "memory_request", lambda *args, **kwargs: pytest.fail("Persistence validation attempted a replacement write"))
    with pytest.raises(RuntimeError, match="checkpoint|lost or changed|owner changed"):
        acceptance.check_semantic_memory("http://demo", True, path)
