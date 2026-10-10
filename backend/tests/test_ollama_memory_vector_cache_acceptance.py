"""Real-provider cache contracts use controlled protocol vectors in CI."""

import json
from types import SimpleNamespace

import pytest
import requests

from app import check_ollama_memory_vector_cache as acceptance
from app.models.execution_snapshot import ExecutionSnapshot
from app.models.memory_vector_cache import MemoryVectorCache
from app.services import semantic_memory
from app.services.memory_vector_cache import namespace
from test_mcp_runtime_api import demo_api  # noqa: F401
from test_ollama_memory_acceptance import database_rows, prepared  # noqa: F401


@pytest.fixture
def cache_acceptance(prepared, monkeypatch):
    monkeypatch.setattr(acceptance, "SessionLocal", prepared.sessions)
    prepared.digest = "a" * 64
    def get(session, url, **kwargs):
        assert url.endswith("/api/tags")
        return SimpleNamespace(status_code=200, json=lambda: {"models": [
            {"name": "embeddinggemma:latest", "digest": prepared.digest}]})
    monkeypatch.setattr(requests.Session, "get", get)
    prepared.cache_file = prepared.path.with_name("ollama-cache.json")
    return prepared


def check(fixture, *, verify=False):
    return acceptance.check_ollama_memory_vector_cache("http://test", verify, fixture.cache_file, fixture.path)


def test_population_then_read_only_restart_preserves_every_original_row(cache_acceptance):
    fixture = cache_acceptance
    source = fixture.path.read_bytes()
    original = database_rows(fixture.sessions)
    first = check(fixture)
    assert first["checks_passed"] == len(first["checks"]) == 8
    assert first["read_only"] is first["persistence_verified"] is False
    assert first["chat_executions_created"] == 0 and first["cache_rows_written"] > 0
    assert first["warm_cache_hits"] > 0
    assert first["warm_cache_misses"] == first["warm_cache_written"] == 0
    assert first["warm_embedding_inputs"] == 1 and first["vector_dimensions"] == [4]
    assert first["preview_checks_passed"] == 7 and first["preview_read_only"] is True
    assert all(case["embedding_inputs"] == 1 for case in first["warm_cases"].values())
    populated = database_rows(fixture.sessions)
    assert {key: value for key, value in populated.items() if key != "memory_vector_cache"} == {
        key: value for key, value in original.items() if key != "memory_vector_cache"}
    saved = fixture.cache_file.read_bytes()
    fixture.vectors.clear()
    second = check(fixture, verify=True)
    assert second["read_only"] is second["persistence_verified"] is second["checkpoint_reused"] is True
    assert second["cache_rows_written"] == second["chat_executions_created"] == 0
    assert second["source_execution_id"] == first["source_execution_id"]
    assert database_rows(fixture.sessions) == populated
    assert fixture.path.read_bytes() == source and fixture.cache_file.read_bytes() == saved
    # The saved owner documents are never forwarded for embedding during reuse.
    assert fixture.vectors and all(len(body["input"]) == 1 for body in fixture.vectors)
    assert all(body["truncate"] is False for body in fixture.vectors)


@pytest.mark.parametrize("loss", ["checkpoint", "json", "version", "source_checkpoint", "cache_row", "vector_json",
                                 "vector_digest", "vector_timestamp", "snapshot", "model_update", "saved_case", "saved_count"])
def test_restart_loss_is_rejected_before_any_embedding_or_repair(cache_acceptance, loss):
    fixture = cache_acceptance
    check(fixture)
    saved = json.loads(fixture.cache_file.read_bytes())
    if loss == "checkpoint": fixture.cache_file.unlink()
    if loss == "json": fixture.cache_file.write_text("invalid")
    if loss == "version": saved["version"] = True; fixture.cache_file.write_text(json.dumps(saved))
    if loss == "source_checkpoint": fixture.path.write_bytes(fixture.path.read_bytes() + b" ")
    if loss == "saved_case": saved["warm_cases"].pop("same_user"); fixture.cache_file.write_text(json.dumps(saved))
    if loss == "saved_count":
        case = saved["warm_cases"]["agent_english"]["cache"]
        case["documents"] += 1; case["hits"] += 1
        fixture.cache_file.write_text(json.dumps(saved))
    if loss == "model_update": fixture.digest = "b" * 64
    with fixture.sessions() as db:
        row = db.query(MemoryVectorCache).filter_by(source_type="agent", owner_id=fixture.state["agent_id"],
            memory_id=fixture.state["private"]["id"], namespace=namespace(acceptance.get_embedding_settings())).one()
        if loss == "cache_row": db.delete(row)
        if loss == "vector_json": row.vector_json = "[NaN,0,0,0]"
        if loss == "vector_digest": row.model_digest = "c" * 64
        if loss == "vector_timestamp": row.created_at = row.created_at.replace(year=2020)
        if loss == "snapshot": db.query(ExecutionSnapshot).filter_by(execution_id=fixture.state["execution_id"]).delete()
        db.commit()
    before = database_rows(fixture.sessions)
    fixture.vectors.clear()
    with pytest.raises((RuntimeError, ValueError)):
        check(fixture, verify=True)
    assert fixture.vectors == [] and database_rows(fixture.sessions) == before


@pytest.mark.parametrize("environment,value", [("LLM_PROVIDER", "mock"), ("MEMORY_RETRIEVAL_MODE", "keyword"),
                                              ("MEMORY_VECTOR_CACHE_ENABLED", "false")])
def test_disabled_or_mock_configuration_fails_before_http(cache_acceptance, monkeypatch, environment, value):
    fixture = cache_acceptance
    monkeypatch.setenv(environment, value)
    fixture.reads.clear()
    with pytest.raises(RuntimeError, match="Ollama backend"):
        check(fixture)
    assert fixture.reads == fixture.vectors == []
    assert not fixture.cache_file.exists()


def test_missing_model_identity_fails_without_populating_cache(cache_acceptance, monkeypatch):
    fixture = cache_acceptance
    monkeypatch.setattr(requests.Session, "get", lambda *args, **kwargs: SimpleNamespace(status_code=404))
    before = database_rows(fixture.sessions)
    with pytest.raises(RuntimeError, match="model digest"):
        check(fixture)
    assert fixture.vectors == [] and database_rows(fixture.sessions) == before


def test_same_user_shares_vector_identity_and_foreign_user_stays_separate(cache_acceptance):
    fixture = cache_acceptance
    first = check(fixture)
    saved = json.loads(fixture.cache_file.read_bytes())
    shared = saved["warm_cases"]["same_user"]["memory_context"]["shared_memories"]
    isolated = saved["warm_cases"]["isolated_user"]["memory_context"]["shared_memories"]
    assert any(row["memory_id"] == fixture.state["shared"]["id"] for row in shared)
    assert all(row["scope_id"] == fixture.state["user_id"] for row in shared)
    assert all(row["scope_id"] == fixture.state["isolation_user_id"] for row in isolated)
    assert first["warm_cases"]["same_user"]["cache"]["misses"] == 0
    with fixture.sessions() as db:
        assert db.query(MemoryVectorCache).filter_by(source_type="user", owner_id=fixture.state["user_id"],
            memory_id=fixture.state["shared"]["id"], namespace=namespace(acceptance.get_embedding_settings())).count() == 1


def test_existing_mock_namespace_is_preserved(cache_acceptance):
    fixture = cache_acceptance
    with fixture.sessions() as db:
        row = MemoryVectorCache(source_type="agent", owner_id=fixture.state["agent_id"], memory_id=fixture.state["private"]["id"],
            namespace="d" * 64, model_digest="e" * 64, content_hash="f" * 64, source_created_at=fixture.state["private"]["created_at"],
            dimensions=4, vector_json="[1,0,0,0]", vector_hash="0" * 64)
        from datetime import datetime
        row.source_created_at = datetime.fromisoformat(row.source_created_at)
        db.add(row); db.commit()
    before = acceptance.database_fingerprints()[1]
    check(fixture)
    after = acceptance.database_fingerprints()[1]
    assert all(after[key] == value for key, value in before.items())


def test_observer_is_restored_on_embedding_failure(cache_acceptance, monkeypatch):
    fixture = cache_acceptance
    original = semantic_memory.embed_texts
    def failed(*args, **kwargs):
        from app.services.memory_embeddings import SemanticMemoryUnavailable
        raise SemanticMemoryUnavailable("Embedding unavailable")
    monkeypatch.setattr(semantic_memory, "embed_texts", failed)
    before = database_rows(fixture.sessions)
    with pytest.raises(RuntimeError, match="fell back"):
        acceptance.runtime_case(acceptance.cases_for(fixture.state)["agent_english"],
                                acceptance.get_embedding_settings(), populate=True)
    assert semantic_memory.embed_texts is failed
    assert database_rows(fixture.sessions) == before
    assert original is not failed and not fixture.cache_file.exists()


def test_initial_run_accepts_already_warmed_documents_without_overwriting_them(cache_acceptance):
    fixture = cache_acceptance
    check(fixture)
    fixture.cache_file.unlink()
    before = database_rows(fixture.sessions)
    result = check(fixture)
    assert result["cache_rows_written"] == 0 and result["warm_embedding_inputs"] == 1
    assert database_rows(fixture.sessions) == before


def test_source_checkpoint_path_cannot_be_overwritten(cache_acceptance):
    fixture = cache_acceptance
    source = fixture.path.read_bytes()
    with pytest.raises(RuntimeError, match="separate JSON"):
        acceptance.check_ollama_memory_vector_cache("http://test", state_file=fixture.path, semantic_state_file=fixture.path)
    assert fixture.path.read_bytes() == source and fixture.vectors == []


def test_unrelated_business_record_change_also_fails_before_embedding(cache_acceptance):
    from app.models.project import Project
    fixture = cache_acceptance
    check(fixture)
    with fixture.sessions() as db:
        db.query(Project).first().description = "An unrelated edit after acceptance"
        db.commit()
    before = database_rows(fixture.sessions)
    fixture.vectors.clear()
    with pytest.raises(RuntimeError, match="will not repair"):
        check(fixture, verify=True)
    assert fixture.vectors == [] and database_rows(fixture.sessions) == before


def test_running_provider_mismatch_fails_before_local_cache_writes(cache_acceptance, monkeypatch):
    fixture = cache_acceptance
    original = fixture.get
    def mismatched(api, path):
        value = original(api, path)
        if "/semantic-search?" in path:
            value["provider"] = "mock"
        return value
    monkeypatch.setattr(acceptance.quality.ReadOnlyAPI, "get", mismatched)
    before = database_rows(fixture.sessions)
    with pytest.raises(RuntimeError, match="real Ollama"):
        check(fixture)
    assert database_rows(fixture.sessions) == before and not fixture.cache_file.exists()


def test_changed_model_during_embedding_never_repairs_a_saved_checkpoint(cache_acceptance, monkeypatch):
    fixture = cache_acceptance
    check(fixture)
    checkpoint = fixture.cache_file.read_bytes()
    before = database_rows(fixture.sessions)
    original = requests.Session.post
    def replaced(session, url, **kwargs):
        response = original(session, url, **kwargs)
        fixture.digest = "b" * 64
        return response
    monkeypatch.setattr(requests.Session, "post", replaced)
    with pytest.raises(RuntimeError, match="HTTP 503|fell back|changed"):
        check(fixture, verify=True)
    assert fixture.cache_file.read_bytes() == checkpoint and database_rows(fixture.sessions) == before
