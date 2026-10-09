"""Real-provider contract checks use controlled vectors, never a learned model."""

import json
import math
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
import requests

from app import check_demo, check_ollama_memory as acceptance, check_semantic_memory, check_user_memory
from app.database import Base
from app.services.memory_embeddings import mock_vector
from test_mcp_runtime_api import demo_api  # noqa: F401


def database_rows(sessions):
    with sessions() as db:
        return {table.name: [tuple(row) for row in db.execute(table.select().order_by(table.c.id))]
                for table in Base.metadata.sorted_tables}


@pytest.fixture
def prepared(demo_api, monkeypatch, tmp_path):
    client, ids, sessions = demo_api
    def read(base, path, payload=None):
        response = client.get(path) if payload is None else client.post(path, json=payload)
        assert response.status_code == 200, response.text
        return response.json()
    def write(base, path, payload=None, *, method=None, status=200):
        response = client.request(method or ("POST" if payload is not None else "GET"), path, json=payload)
        assert response.status_code == status, response.text
        return response.json()
    for module in (check_demo, check_semantic_memory, check_user_memory):
        monkeypatch.setattr(module, "request_json", read)
    monkeypatch.setattr(check_semantic_memory, "memory_request", write)
    monkeypatch.setenv("MEMORY_RETRIEVAL_MODE", "semantic")
    path = tmp_path / "semantic-memory-acceptance.json"
    check_semantic_memory.check_semantic_memory("http://test", state_file=path)
    client.post("/memories", json={"agent_id": ids["agent_id"], "content": check_semantic_memory.SHARED})
    state = json.loads(path.read_bytes())
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    vectors, reads = [], []
    def post(session, url, **kwargs):
        body = kwargs["json"]
        vectors.append(body)
        values = [[0, 1, 0, 0] if text == acceptance.CONTROL_QUERY else list(mock_vector(text)) for text in body["input"]]
        return SimpleNamespace(status_code=200, json=lambda: {"model": body["model"], "embeddings": values})
    monkeypatch.setattr(requests.Session, "post", post)
    def get(api, requested):
        api.requests_made += 1
        reads.append(requested)
        response = client.get(requested)
        if response.status_code != 200:
            raise RuntimeError(f"GET {requested} returned HTTP {response.status_code}: {response.json()}")
        return response.json()
    monkeypatch.setattr(acceptance.ReadOnlyAPI, "get", get)
    return SimpleNamespace(client=client, ids=ids, sessions=sessions, path=path, state=state, vectors=vectors, reads=reads, get=get)


def test_real_provider_contract_reports_quality_and_preserves_every_table_and_checkpoint(prepared):
    before, checkpoint = database_rows(prepared.sessions), prepared.path.read_bytes()
    result = acceptance.check_ollama_memory("http://test", prepared.path)
    assert result["checks_passed"] == len(result["checks"]) == 7
    assert result["embedding_provider"] == "ollama" and result["embedding_model"] == "embeddinggemma"
    assert result["read_only"] is True and result["chat_executions_created"] == 0
    assert [row["scenario"] for row in result["evidence"]] == ["Agent English paraphrase", "Shared Chinese paraphrase", "Same-user English to Chinese"]
    assert result["evidence"][0]["rank"] == 2
    assert all(row["similarity"] == 0.96 for row in result["evidence"])
    assert all(row["control_similarity"] is None for row in result["evidence"])
    assert prepared.vectors and all(body["truncate"] is False for body in prepared.vectors)
    assert database_rows(prepared.sessions) == before and prepared.path.read_bytes() == checkpoint


def test_measured_control_similarity_and_margin_are_reported(prepared, monkeypatch):
    def post(session, url, **kwargs):
        body = kwargs["json"]
        values = [[0.2, math.sqrt(0.96), 0, 0] if text == acceptance.CONTROL_QUERY else list(mock_vector(text)) for text in body["input"]]
        return SimpleNamespace(status_code=200, json=lambda: {"model": body["model"], "embeddings": values})
    monkeypatch.setattr(requests.Session, "post", post)
    result = acceptance.check_ollama_memory("http://test", prepared.path)
    assert all(row["control_similarity"] == 0.2 and row["similarity_margin"] == 0.76 for row in result["evidence"][:2])
    assert result["evidence"][2]["control_similarity"] is None


def test_configured_embedding_model_is_reported_without_changing_agent_chat_model(prepared, monkeypatch):
    monkeypatch.setenv("OLLAMA_EMBEDDING_MODEL", "local-custom:latest")
    result = acceptance.check_ollama_memory("http://test", prepared.path)
    assert result["embedding_model"] == "local-custom:latest"
    assert all(body["model"] == "local-custom:latest" for body in prepared.vectors)
    assert all(row["model"] == "qwen2.5:7b" for row in prepared.client.get("/agents").json())


@pytest.mark.parametrize("fault", ["provider", "model", "mode", "runtime", "agent", "limit", "threshold", "score_nan", "score_bool", "score_large", "score_low", "duplicate", "order", "scope", "identity", "content", "count", "shared_owner"])
def test_invalid_preview_metadata_scores_and_scope_fail_without_writes(prepared, monkeypatch, fault):
    before, checkpoint = database_rows(prepared.sessions), prepared.path.read_bytes()
    def get(api, path):
        result = prepared.get(api, path)
        if "/semantic-search?" not in path:
            return result
        if fault == "shared_owner":
            if path.startswith("/user-memories/"): result["user_id"] += 1
            return result
        values = {"provider": ("provider", "mock"), "model": ("model", "wrong"), "mode": ("mode", "keyword"),
                  "runtime": ("runtime_mode", "keyword"), "agent": ("agent_id", 999), "limit": ("limit", 6),
                  "threshold": ("min_similarity", math.nan)}
        if fault in values:
            key, value = values[fault]
            result[key] = value
        elif fault.startswith("score_"):
            result["results"][0]["similarity"] = {"score_nan": math.nan, "score_bool": True, "score_large": 1.1, "score_low": 0.1}[fault]
        elif fault == "duplicate": result["results"].append(result["results"][0])
        elif fault == "order": result["results"].reverse()
        elif fault == "scope": result["results"][0]["memory"]["agent_id"] = 999
        elif fault == "identity": result["results"][0]["memory"]["id"] = 999
        elif fault == "content": result["results"][0]["memory"]["content"] = "Changed outside saved scope"
        elif fault == "count": result["results"] *= 3
        return result
    monkeypatch.setattr(acceptance.ReadOnlyAPI, "get", get)
    with pytest.raises(RuntimeError): acceptance.check_ollama_memory("http://test", prepared.path)
    assert database_rows(prepared.sessions) == before and prepared.path.read_bytes() == checkpoint


@pytest.mark.parametrize("failure", ["all_vectors_equal", "weak_relevant", "control_stronger", "model_missing"])
def test_quality_or_model_failures_never_report_success_or_modify_fixtures(prepared, monkeypatch, failure):
    before, checkpoint = database_rows(prepared.sessions), prepared.path.read_bytes()
    def post(session, url, **kwargs):
        body = kwargs["json"]
        if failure == "model_missing":
            return SimpleNamespace(status_code=404, json=lambda: {"error": "not installed"})
        values = []
        for text in body["input"]:
            value = list(mock_vector(text))
            if failure == "all_vectors_equal": value = [1, 0, 0, 0]
            elif text == acceptance.QUERY: value = [0.2, math.sqrt(0.96), 0, 0] if failure == "weak_relevant" else [0.7, math.sqrt(0.51), 0, 0]
            elif text == acceptance.CONTROL_QUERY: value = [0.8, 0.6, 0, 0]
            values.append(value)
        return SimpleNamespace(status_code=200, json=lambda: {"model": body["model"], "embeddings": values})
    monkeypatch.setattr(requests.Session, "post", post)
    with pytest.raises(RuntimeError, match="quality|threshold|HTTP 503"):
        acceptance.check_ollama_memory("http://test", prepared.path)
    assert database_rows(prepared.sessions) == before and prepared.path.read_bytes() == checkpoint


@pytest.mark.parametrize("loss", ["checkpoint", "json", "version", "id", "same_agent", "private", "shared", "isolated", "timestamp", "snapshot"])
def test_missing_or_changed_checkpoint_fixtures_fail_before_embedding_calls(prepared, monkeypatch, loss):
    state = prepared.state
    if loss == "checkpoint": prepared.path.unlink()
    elif loss == "json": prepared.path.write_text("not JSON")
    else:
        if loss == "version": state["version"] = True
        if loss == "id": state["agent_id"] = True
        if loss == "same_agent": state["peer_agent_id"] = state["agent_id"]
        if loss in ("private", "shared", "isolated"): state[loss]["id"] += 1000
        if loss == "timestamp": state["private"]["created_at"] = "changed"
        prepared.path.write_text(json.dumps(state))
    if loss == "snapshot":
        def get(api, path):
            if path.endswith("/snapshot"): raise RuntimeError("HTTP 404: Snapshot lost")
            return prepared.get(api, path)
        monkeypatch.setattr(acceptance.ReadOnlyAPI, "get", get)
    before = database_rows(prepared.sessions)
    with pytest.raises((RuntimeError, ValueError)): acceptance.check_ollama_memory("http://test", prepared.path)
    assert prepared.vectors == [] and database_rows(prepared.sessions) == before


def test_mock_backend_process_is_rejected_before_any_http(prepared, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    prepared.reads.clear()
    with pytest.raises(RuntimeError, match="without the Mock override"):
        acceptance.check_ollama_memory("http://test", prepared.path)
    assert prepared.reads == [] and prepared.vectors == []


def test_checkpoint_change_during_preview_is_detected_and_never_repaired(prepared, monkeypatch):
    changed = prepared.path.read_bytes() + b" "
    def get(api, path):
        result = prepared.get(api, path)
        if "/semantic-search?" in path: prepared.path.write_bytes(changed)
        return result
    monkeypatch.setattr(acceptance.ReadOnlyAPI, "get", get)
    before = database_rows(prepared.sessions)
    with pytest.raises(RuntimeError, match="changed during the read-only check"):
        acceptance.check_ollama_memory("http://test", prepared.path)
    assert prepared.path.read_bytes() == changed and database_rows(prepared.sessions) == before


@pytest.mark.parametrize("timeout", [0, -1, math.inf, math.nan])
def test_invalid_http_timeout_is_rejected(timeout):
    with pytest.raises(RuntimeError, match="timeout"):
        acceptance.ReadOnlyAPI("http://127.0.0.1:8000", timeout)


def test_read_only_http_transport_bypasses_proxies_and_rejects_html_errors_and_redirects(monkeypatch):
    seen = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append((self.command, self.path))
            status = 302 if self.path == "/redirect" else 503 if self.path == "/error" else 200
            content_type = "text/html" if self.path == "/html" else "application/json"
            payload = b"invalid" if self.path == "/invalid" else json.dumps({"detail": "local model unavailable"}).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            if self.path == "/redirect": self.send_header("Location", "/ok")
            self.end_headers()
            self.wfile.write(payload)
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    try:
        api = acceptance.ReadOnlyAPI(f"http://127.0.0.1:{server.server_port}", 2)
        assert api.get("/ok") == {"detail": "local model unavailable"}
        for path, message in (("/html", "non-JSON"), ("/error", "HTTP 503"), ("/redirect", "HTTP 302")):
            with pytest.raises(RuntimeError, match=message): api.get(path)
        with pytest.raises(ValueError): api.get("/invalid")
        assert seen == [("GET", path) for path in ("/ok", "/html", "/error", "/redirect", "/invalid")]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
