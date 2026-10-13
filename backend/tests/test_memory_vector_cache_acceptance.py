"""Cache persistence is checked before the verification chat can repair anything."""

import json
from urllib.error import HTTPError

import pytest

from app import check_memory_vector_cache as acceptance
from app import check_memory_evidence
from app.models.execution_log import ExecutionLog
from app.models.execution_snapshot import ExecutionSnapshot
from app.models.memory_vector_cache import MemoryVectorCache
from test_memory_evidence import database_rows
from test_memory_evidence_acceptance import evidence_acceptance  # noqa: F401
from test_mcp_runtime_api import demo_api  # noqa: F401


@pytest.fixture
def vector_acceptance(evidence_acceptance, monkeypatch):
    client, ids, sessions, source_file, _, writes, source = evidence_acceptance
    monkeypatch.setattr(acceptance, "SessionLocal", sessions)
    monkeypatch.setattr(acceptance, "request_json", check_memory_evidence.request_json)
    monkeypatch.setattr(acceptance, "memory_request", check_memory_evidence.memory_request)
    return client, ids, sessions, source_file, source_file.with_name("vector-acceptance.json"), writes, source


def test_initial_and_restart_checks_reuse_original_vectors_and_inspections(vector_acceptance):
    _, _, sessions, source_file, state_file, writes, _ = vector_acceptance
    source_bytes = source_file.read_bytes()
    first = acceptance.check_memory_vector_cache("http://demo", False, state_file, source_file)
    assert first["checks_passed"] == 7 and first["chat_executions_created"] == 6
    assert first["cache_hits"] == 2 and first["cache_misses"] == first["cache_written"] == 0
    saved = state_file.read_bytes()
    with sessions() as db:
        cache_before = [acceptance.cache_record(row) for row in db.query(MemoryVectorCache).order_by(MemoryVectorCache.id)]
    writes.clear()
    second = acceptance.check_memory_vector_cache("http://demo", True, state_file, source_file)
    assert second["persistence_verified"] is True and second["original_execution_ids"] == first["original_execution_ids"]
    assert second["chat_executions_created"] == len(writes) == 1 and second["cache_hits"] == 2
    assert state_file.read_bytes() == saved and source_file.read_bytes() == source_bytes
    with sessions() as db:
        assert [acceptance.cache_record(row) for row in db.query(MemoryVectorCache).order_by(MemoryVectorCache.id)] == cache_before


@pytest.mark.parametrize("loss", ["checkpoint", "checkpoint_json", "checkpoint_version", "source_checkpoint",
                                 "vector", "vector_json", "vector_digest", "vector_timestamp", "source_snapshot",
                                 "execution_snapshot", "cache_log", "capture"])
def test_restart_loss_fails_before_a_chat_can_recreate_vectors(vector_acceptance, loss):
    _, _, sessions, source_file, state_file, writes, source = vector_acceptance
    acceptance.check_memory_vector_cache("http://demo", False, state_file, source_file)
    state = json.loads(state_file.read_text())
    if loss == "checkpoint": state_file.unlink()
    if loss == "checkpoint_json": state_file.write_text("{invalid")
    if loss == "checkpoint_version": state["version"] = 99; state_file.write_text(json.dumps(state))
    if loss == "source_checkpoint": source_file.unlink()
    with sessions() as db:
        row = db.query(MemoryVectorCache).filter_by(source_type="agent", memory_id=source["private"]["id"]).one()
        if loss == "vector": db.delete(row)
        if loss == "vector_json": row.vector_json = "[NaN,0,0,0]"
        if loss == "vector_digest": row.model_digest = "a" * 64
        if loss == "vector_timestamp": row.created_at = row.created_at.replace(year=2020)
        if loss in {"source_snapshot", "execution_snapshot"}:
            chosen = source["execution_id"] if loss == "source_snapshot" else state["cases"]["warm"]["execution_id"]
            db.query(ExecutionSnapshot).filter_by(execution_id=chosen).delete()
        if loss in {"cache_log", "capture"}:
            prefix = "memory_embedding_cache:" if loss == "cache_log" else "memory_retrieval_details:"
            db.query(ExecutionLog).filter(ExecutionLog.execution_id == state["cases"]["warm"]["execution_id"],
                ExecutionLog.message.like(prefix + "%")).delete()
        db.commit()
    before = database_rows(sessions); writes.clear()
    with pytest.raises((RuntimeError, ValueError, HTTPError)):
        acceptance.check_memory_vector_cache("http://demo", True, state_file, source_file)
    assert writes == [] and database_rows(sessions) == before
