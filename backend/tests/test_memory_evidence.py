"""Evidence must describe the prompt used, survive source edits, and stay scoped."""

from copy import deepcopy
import json

import pytest

from app.models.execution import Execution
from app.models.execution_log import ExecutionLog
from app.models.memory import Memory
from app.services.memory_service import build_memory_context
from app.workers import execution_worker
from test_mcp_runtime_api import demo_api  # noqa: F401
from test_semantic_memory import save, shared
from test_user_memory import add_agent


def chat(client, agent_id, query):
    result = client.post(f"/agents/{agent_id}/chat", json={"message": query})
    assert result.status_code == 200, result.text
    return result.json()


def evidence(client, execution_id, agent_id):
    response = client.get(f"/executions/{execution_id}/memory-context", params={"agent_id": agent_id})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["execution_id"] == execution_id and body["available"] is True
    return body["evidence"]


def database_rows(sessions):
    from app.database import Base
    with sessions() as db:
        return {table.name: [tuple(row) for row in db.execute(table.select().order_by(*table.primary_key.columns))]
                for table in Base.metadata.sorted_tables}


def test_keyword_evidence_is_the_exact_runtime_prompt_and_preview_order(demo_api, monkeypatch):
    client, ids, sessions = demo_api
    agent_id = ids["agent_id"]
    saved = [save(client, agent_id, text) for text in ("Python SQLite concise.", "Python older.", "SQLite newer.")]
    foreign = save(client, ids["mcp_agent_id"], "Python private foreign.")
    common = shared(client, agent_id, ids["user_id"], "Python shared preference.")
    captured = []
    original = execution_worker.run_agent
    def run(*args, **kwargs):
        captured.append(args[2])
        return original(*args, **kwargs)
    monkeypatch.setattr(execution_worker, "run_agent", run)
    result = chat(client, agent_id, "  Python SQLite Python  ")
    facts = evidence(client, result["execution_id"], agent_id)
    assert facts["version"] == 1 and facts["query"] == "Python SQLite Python"
    assert facts["requested_mode"] == facts["mode"] == "keyword"
    assert facts["provider"] is facts["model"] is facts["min_similarity"] is facts["fallback_reason"] is None
    assert [row["memory_id"] for row in facts["agent_memories"]] == [saved[0]["id"], saved[2]["id"], saved[1]["id"]]
    assert [row["score"] for row in facts["agent_memories"]] == [2, 1, 1]
    assert facts["agent_memories"][0]["matched_terms"] == ["python", "sqlite"]
    assert facts["shared_memories"][0]["memory_id"] == common["id"]
    assert all(row["scope_id"] == agent_id for row in facts["agent_memories"])
    assert foreign["content"] not in facts["context"]
    assert captured == [facts["context"]]
    assert facts["context"] == "Shared user memory:\nPython shared preference.\nAgent memory:\nPython SQLite concise.\nSQLite newer.\nPython older."
    before = database_rows(sessions)
    assert evidence(client, result["execution_id"], agent_id) == facts
    assert database_rows(sessions) == before
    trace = client.get(f'/executions/{result["execution_id"]}/trace').json()
    assert [row["event"] for row in trace] == ["plan_started", "step_started", "step_completed", "plan_completed"]
    assert client.get(f'/executions/{result["execution_id"]}/snapshot').json()["snapshot_version"] == 1


def test_semantic_capture_uses_each_scope_budget_and_original_scores(demo_api, monkeypatch):
    client, ids, _ = demo_api
    monkeypatch.setenv("MEMORY_RETRIEVAL_MODE", "semantic")
    private = [save(client, ids["agent_id"], text) for text in ("I prefer concise answers.", "我喜欢简洁的回答。")]
    common = shared(client, ids["agent_id"], ids["user_id"], "我喜欢简洁的回答。")
    result = chat(client, ids["agent_id"], "Keep it brief.")
    facts = evidence(client, result["execution_id"], ids["agent_id"])
    assert (facts["requested_mode"], facts["mode"], facts["provider"], facts["model"], facts["min_similarity"]) == (
        "semantic", "semantic", "mock", "mock-fixtures-v1", 0.35)
    assert [row["memory_id"] for row in facts["agent_memories"]] == [row["id"] for row in reversed(private)]
    assert facts["shared_memories"][0]["memory_id"] == common["id"]
    assert all(row["similarity"] == 0.96 and row["score"] is None and row["matched_terms"] == []
               for row in facts["agent_memories"] + facts["shared_memories"])
    for index in range(7):
        save(client, ids["agent_id"], "Agent scope " + str(index))
        shared(client, ids["agent_id"], ids["user_id"], "User scope " + str(index))
    from app.services import semantic_memory
    monkeypatch.setattr(semantic_memory, "embed_texts", lambda texts, settings: [(1.0, 0.0)] * len(texts))
    result = chat(client, ids["agent_id"], "Keep it brief.")
    facts = evidence(client, result["execution_id"], ids["agent_id"])
    assert len(facts["agent_memories"]) == len(facts["shared_memories"]) == facts["limit"] == 5
    assert "Agent scope 0" not in facts["context"] and "User scope 0" not in facts["context"]


@pytest.mark.parametrize("failure", ["mock_query", "embedding", "configuration"])
def test_fallback_evidence_records_keyword_results_and_real_reason(demo_api, monkeypatch, failure):
    client, ids, _ = demo_api
    save(client, ids["agent_id"], "Python preference.")
    monkeypatch.setenv("MEMORY_RETRIEVAL_MODE", "semantic")
    if failure == "embedding":
        from app.services import semantic_memory
        from app.services.memory_embeddings import SemanticMemoryUnavailable
        def offline(*args): raise SemanticMemoryUnavailable("Local embeddings offline")
        monkeypatch.setattr(semantic_memory, "embed_texts", offline)
        query = "Keep it brief."
    else:
        query = "Python"
        if failure == "configuration": monkeypatch.setenv("MEMORY_SEMANTIC_MIN_SIMILARITY", "nan")
    result = chat(client, ids["agent_id"], query)
    facts = evidence(client, result["execution_id"], ids["agent_id"])
    assert facts["requested_mode"] == "semantic" and facts["mode"] == "keyword" and facts["fallback_reason"]
    assert facts["provider"] is facts["model"] is facts["min_similarity"] is None
    assert facts["context"] == ("" if failure == "embedding" else "Python preference.")
    logs = client.get(f'/executions/{result["execution_id"]}/logs').json()
    assert any(row["level"] == "warning" and facts["fallback_reason"] in row["message"] for row in logs)


def test_historical_evidence_survives_edits_deletions_and_configuration_change(demo_api, monkeypatch):
    client, ids, sessions = demo_api
    private = save(client, ids["agent_id"], "Python original private.")
    common = shared(client, ids["agent_id"], ids["user_id"], "Python original shared.")
    result = chat(client, ids["agent_id"], "Python")
    facts = evidence(client, result["execution_id"], ids["agent_id"])
    paths = ((f'/memories/item/{private["id"]}?agent_id={ids["agent_id"]}', private),
             (f'/user-memories/item/{common["id"]}?agent_id={ids["agent_id"]}&user_id={ids["user_id"]}', common))
    for path, row in paths:
        changed = client.patch(path, json={"content": "Rust edited.", "expected_content": row["content"]})
        assert changed.status_code == 200, changed.text
        assert client.delete(path).status_code == 200
    monkeypatch.setenv("MEMORY_RETRIEVAL_MODE", "semantic")
    before = database_rows(sessions)
    assert evidence(client, result["execution_id"], ids["agent_id"]) == facts
    assert "original private" in facts["context"] and "original shared" in facts["context"]
    assert database_rows(sessions) == before


def test_shared_capture_never_reads_another_user_or_peer_private_memory(demo_api, monkeypatch):
    client, ids, sessions = demo_api
    monkeypatch.setenv("MEMORY_RETRIEVAL_MODE", "semantic")
    own = save(client, ids["agent_id"], "I prefer concise answers.")
    common = shared(client, ids["agent_id"], ids["user_id"], "我喜欢简洁的回答。")
    other_agent, other_owner = add_agent(sessions)
    isolated = shared(client, other_agent, other_owner, "I prefer concise answers.")
    peer_result = chat(client, ids["mcp_agent_id"], "Keep it brief.")
    peer = evidence(client, peer_result["execution_id"], ids["mcp_agent_id"])
    assert peer["agent_memories"] == [] and peer["shared_memories"][0]["memory_id"] == common["id"]
    outsider_result = chat(client, other_agent, "Keep it brief.")
    outsider = evidence(client, outsider_result["execution_id"], other_agent)
    assert outsider["agent_memories"] == [] and outsider["user_id"] == other_owner
    assert outsider["shared_memories"][0]["memory_id"] == isolated["id"]
    assert common["content"] not in outsider["context"] and own["id"] not in [row["memory_id"] for row in peer["agent_memories"]]


@pytest.mark.parametrize("query,limit", [("", 1), ("   ", 5), ("Python", 0), ("Python", -1)])
def test_internal_empty_query_and_zero_budget_keep_legacy_behavior(demo_api, monkeypatch, query, limit):
    client, ids, sessions = demo_api
    private = save(client, ids["agent_id"], "Python original.")
    monkeypatch.setenv("MEMORY_RETRIEVAL_MODE", "semantic")
    captures = []
    with sessions() as db:
        context = build_memory_context(db, ids["agent_id"], query, limit, on_details=captures.append)
    facts = captures[0]
    assert facts.mode == "keyword" and facts.requested_mode == "semantic" and facts.fallback_reason is None
    assert context == (private["content"] if limit > 0 else "") and facts.context == context


def test_empty_successful_semantic_ranking_is_recorded_without_fallback(demo_api, monkeypatch):
    client, ids, _ = demo_api
    monkeypatch.setenv("MEMORY_RETRIEVAL_MODE", "semantic")
    save(client, ids["agent_id"], "I prefer concise answers.")
    result = chat(client, ids["agent_id"], "Unrelated semantic fixture.")
    facts = evidence(client, result["execution_id"], ids["agent_id"])
    assert facts["mode"] == "semantic" and facts["context"] == "" and facts["fallback_reason"] is None
    assert facts["agent_memories"] == facts["shared_memories"] == []


def test_old_cancelled_and_replayed_executions_do_not_fabricate_evidence(demo_api):
    client, ids, sessions = demo_api
    with sessions() as db:
        old = Execution(agent_id=ids["agent_id"], input="Python", status="cancelled")
        db.add(old); db.commit(); old_id = old.id
    execution_worker.execute_agent(old_id)
    body = client.get(f"/executions/{old_id}/memory-context").json()
    assert body == {"execution_id": old_id, "available": False, "evidence": None}
    result = chat(client, ids["agent_id"], "Python")
    replay = client.post(f'/executions/{result["execution_id"]}/replay').json()
    assert client.get(f'/executions/{replay["id"]}/memory-context').json() == {
        "execution_id": replay["id"], "available": False, "evidence": None}


def test_failed_execution_and_internal_retry_retain_the_selected_prompt(demo_api, monkeypatch):
    client, ids, _ = demo_api
    save(client, ids["agent_id"], "Python preference.")
    calls = []
    def fail(*args, **kwargs):
        calls.append(args[2])
        raise TimeoutError("model timed out")
    monkeypatch.setattr(execution_worker, "run_agent", fail)
    result = chat(client, ids["agent_id"], "Python")
    assert result["status"] == "failed" and len(calls) > 1
    facts = evidence(client, result["execution_id"], ids["agent_id"])
    assert calls == [facts["context"]] * len(calls)
    logs = client.get(f'/executions/{result["execution_id"]}/logs').json()
    assert sum(row["message"].startswith("memory_retrieval_details: ") for row in logs) == 1


@pytest.mark.parametrize("corruption", ["json", "version", "agent", "query", "owner", "scope", "duplicate", "limit",
                                        "score", "terms", "nan", "context", "provider", "semantic", "timestamp", "boolean_id"])
def test_invalid_latest_evidence_returns_409_instead_of_current_memories(demo_api, corruption):
    client, ids, sessions = demo_api
    save(client, ids["agent_id"], "Python original.")
    common = shared(client, ids["agent_id"], ids["user_id"], "Python shared.")
    result = chat(client, ids["agent_id"], "Python")
    facts = deepcopy(evidence(client, result["execution_id"], ids["agent_id"]))
    row = facts["agent_memories"][0]
    if corruption == "version": facts["version"] = 99
    if corruption == "agent": facts["agent_id"] = ids["mcp_agent_id"]
    if corruption == "query": facts["query"] = "Rust"
    if corruption == "owner": facts["user_id"] += 100
    if corruption == "scope": row["scope_id"] += 100
    if corruption == "duplicate": facts["agent_memories"].append(deepcopy(row))
    if corruption == "limit": facts["limit"] = 0
    if corruption == "score": row["score"] = 0
    if corruption == "terms": row["matched_terms"] = ["python", "python"]
    if corruption == "nan": row["similarity"] = float("nan")
    if corruption == "context": facts["context"] = common["content"]
    if corruption == "provider": facts["provider"] = "ollama"
    if corruption == "semantic": facts["mode"] = "semantic"
    if corruption == "timestamp": row["created_at"] = "invalid"
    if corruption == "boolean_id": row["memory_id"] = True
    message = "memory_retrieval_details: " + ("{invalid" if corruption == "json" else json.dumps(facts))
    with sessions() as db:
        db.add(ExecutionLog(execution_id=result["execution_id"], message=message)); db.commit()
    before = database_rows(sessions)
    response = client.get(f'/executions/{result["execution_id"]}/memory-context')
    assert response.status_code == 409 and "cannot be reconstructed" in response.json()["detail"]
    assert database_rows(sessions) == before
    # Scope rejection precedes parsing a possibly corrupt private log.
    assert client.get(f'/executions/{result["execution_id"]}/memory-context?agent_id={ids["mcp_agent_id"]}').status_code == 404


@pytest.mark.parametrize("path", ["/executions/0/memory-context", "/executions/-1/memory-context",
                                  "/executions/1/memory-context?agent_id=0", "/executions/1/memory-context?agent_id=bad"])
def test_invalid_positive_ids_are_read_only_422(demo_api, path):
    client, _, sessions = demo_api
    before = database_rows(sessions)
    assert client.get(path).status_code == 422
    assert database_rows(sessions) == before


def test_missing_execution_is_read_only_404(demo_api):
    client, _, sessions = demo_api
    before = database_rows(sessions)
    assert client.get("/executions/999999/memory-context").status_code == 404
    assert database_rows(sessions) == before
